from contextlib import contextmanager

import frappe

from erpnext.buying.doctype.supplier_scorecard.supplier_scorecard import daterange
from frappe import _
from frappe.utils import add_days, cint, date_diff, format_date, getdate
from hrms.hr.doctype.leave_application.leave_application import (
    AttendanceAlreadyMarkedError,
    InsufficientLeaveBalanceError,
    LeaveApplication,
    get_approved_leaves_for_period,
    get_leave_balance_on,
    get_number_of_leave_days,
    is_lwp,
)

from real_group_hrms.doc_events.attendance import (
    allocate_c_off,
    update_attendance_tag,
)
from real_group_hrms.helper.attendance_helper import create_attendance
from real_group_hrms.utils import (
    get_actual_leave_balance_cf,
    get_holiday_dates_for_employee,
    holiday_matches_requested_half,
    is_holiday_for_employee,
)


@contextmanager
def suppress_incentive_allocation():
    previous_sync_state = getattr(
        frappe.flags, "in_leave_application_attendance_sync", False
    )
    frappe.flags.in_leave_application_attendance_sync = True
    try:
        yield
    finally:
        frappe.flags.in_leave_application_attendance_sync = previous_sync_state


class LeaveApplicationOverride(LeaveApplication):
    def validate(self):
        super().validate()
        self.validate_half_type_required()
        self.validate_joining_date()

    def validate_half_type_required(self):
        if cint(self.half_day) and not (self.custom_half_type or "").strip():
            frappe.throw(_("Half Type is mandatory when Half Day is selected."))

    def validate_joining_date(self):
        joining_date = frappe.db.get_value("Employee", self.employee, "date_of_joining")
        if joining_date and getdate(self.from_date) < joining_date:
            frappe.throw(
                _("Leave cannot be applied before employee's joining date: {0}").format(
                    format_date(joining_date)
                )
            )

    def validate_applicable_after(self):
        if not self.leave_type:
            return

        leave_type = frappe.get_doc("Leave Type", self.leave_type)
        if leave_type.applicable_after <= 0:
            return

        date_of_joining = frappe.db.get_value(
            "Employee", self.employee, "date_of_joining"
        )
        if not date_of_joining:
            return

        leave_days = get_approved_leaves_for_period(
            self.employee, False, date_of_joining, self.from_date
        )
        number_of_days = date_diff(getdate(self.from_date), date_of_joining)
        if number_of_days < 0:
            return

        holidays = 0
        if not leave_type.include_holiday:
            holidays = self.get_public_holidays(date_of_joining, self.from_date)

        number_of_days = number_of_days - leave_days - holidays
        if number_of_days < leave_type.applicable_after:
            frappe.throw(
                _("{0} applicable after {1} working days").format(
                    self.leave_type, leave_type.applicable_after
                )
            )

    def get_public_holidays(self, from_date, to_date):
        return len(get_holiday_dates_for_employee(self.employee, from_date, to_date))

    def process_jobs_after_update(self, doc):
        frappe.enqueue(
            update_attendance_tag, doc=doc, queue="long", enqueue_after_commit=True
        )
        frappe.enqueue(allocate_c_off, doc=doc, queue="long", enqueue_after_commit=True)

    def update_attendance(self):
        if self.status != "Approved":
            return

        grade = frappe.get_value("Employee", self.employee, "grade")
        apply_sandwich = frappe.db.get_value(
            "Employee Grade", grade, "custom_sandwich_flag"
        )

        from_date = getdate(self.from_date)
        to_date = getdate(self.to_date)

        # Fetch all dates in range
        all_dates = [d for d in daterange(from_date, to_date)]

        # Build holiday map: must include half-day info
        holiday_map = {}
        for d in all_dates:
            info = is_holiday_for_employee(self.employee, d) or {}
            holiday_map[d] = {
                "is_holiday": bool(info.get("is_holiday")),
                "is_half_day": bool(info.get("is_half_day")),
                "half_type": info.get("half_type"),
            }

        # Initial status map
        status = {}
        for d in all_dates:
            if self.half_day and getdate(self.half_day_date) == d:
                status[d] = "half_leave"
            elif holiday_map[d]["is_holiday"]:
                status[d] = (
                    "half_holiday" if holiday_map[d]["is_half_day"] else "full_holiday"
                )
            else:
                status[d] = "full_leave"

        if apply_sandwich:
            for d in all_dates:
                if status[d] == "full_holiday":
                    status[d] = "full_leave"
        else:
            # Remove holidays entirely if sandwich is NOT applied
            holiday_dates = get_holiday_dates_for_employee(
                self.employee, self.from_date, self.to_date
            )
            all_dates = [
                d for d in all_dates if d.strftime("%Y-%m-%d") not in holiday_dates
            ]
        for d in all_dates:
            date_str = d.strftime("%Y-%m-%d")
            attendance_name = frappe.db.exists(
                "Attendance",
                {
                    "employee": self.employee,
                    "attendance_date": date_str,
                    "docstatus": ("!=", 2),
                },
            )

            day_status = status[d]

            # Holidays should not create attendance when sandwich disabled
            if day_status == "full_holiday":
                continue

            # For sandwich → converted holidays are now full_leave → mark absent
            # if apply_sandwich and day_status == "full_leave" and holiday_map[d]["is_holiday"]:
            #     self.create_or_update_attendance(attendance_name, date_str, status="Absent")
            #     continue

            # Normal leave or half-day logic
            is_lwp = frappe.db.get_value("Leave Type", self.leave_type, "is_lwp")

            if self.half_day and getdate(self.half_day_date) == d:
                final_status = "Half Day"
            elif is_lwp:
                final_status = "Absent"
            else:
                final_status = "On Leave"

            self.create_or_update_attendance(
                attendance_name, date_str, status=final_status
            )

    def create_or_update_attendance(self, attendance_name, date, status="On Leave"):
        if attendance_name:
            # update existing attendance, change absent to on leave
            doc = frappe.get_doc("Attendance", attendance_name)
            final_status = status
            holiday = is_holiday_for_employee(self.employee, date) or {}
            current_leave_is_lwp = frappe.db.get_value("Leave Type", self.leave_type, "is_lwp")
            existing_leave_is_lwp = (
                frappe.db.get_value("Leave Type", doc.leave_type, "is_lwp") if doc.leave_type else 0
            )

            # Match Attendance Request behavior for half-day merge:
            # existing half-day attendance + half-day leave => present,
            # but only when the existing half is actually backed by presence
            # (an Attendance Request - e.g. half-day OD/Tour). Two pure leave
            # halves (e.g. half-day EL + half-day CO) involve no physical
            # presence at all, so they should combine into "On Leave", not
            # "Present" - the employee didn't work either half of the day.
            if doc.status == "Half Day" and status == "Half Day":
                if (
                    not current_leave_is_lwp
                    and not existing_leave_is_lwp
                    and not holiday_matches_requested_half(holiday, self.custom_half_type)
                ):
                    final_status = "Present" if doc.attendance_request else "On Leave"

            doc.db_set(
                {
                    "status": final_status,
                    "leave_type": self.leave_type,
                    "leave_application": self.name,
                    "custom_half_type": (
                        self.custom_half_type
                        if self.half_day_date
                        and getdate(date) == getdate(self.half_day_date)
                        else None
                    ),
                }
            )
            self.process_jobs_after_update(doc)
        else:
            # make new attendance and submit it
            doc = frappe.new_doc("Attendance")
            doc.employee = self.employee
            doc.employee_name = self.employee_name
            doc.attendance_date = date
            doc.company = self.company
            doc.leave_type = self.leave_type
            doc.leave_application = self.name
            doc.status = status
            doc.custom_half_type = (
                self.custom_half_type
                if self.half_day_date and getdate(date) == getdate(self.half_day_date)
                else None
            )
            doc.flags.ignore_validate = True
            doc.insert(ignore_permissions=True)
            doc.submit()

    def cancel_attendance(self):
        if self.docstatus != 2:
            return
        if getattr(frappe.flags, "in_reprocess_attendance", False):
            return
        from frappe.utils import getdate

        Attendance = frappe.qb.DocType("Attendance")

        # Fetch all attendance records linked to this leave application
        result = (
            frappe.qb.from_(Attendance)
            .select(Attendance.name, Attendance.attendance_date)
            .where(
                (Attendance.employee == self.employee)
                & (Attendance.attendance_date.between(self.from_date, self.to_date))
                & (Attendance.docstatus < 2)
                & (
                    (Attendance.status.isin(["On Leave", "Half Day"]))
                    | (Attendance.leave_application == self.name)
                )
            )
            .run(as_dict=True)
        )

        if not result:
            return
        checkin_map = {}
        for row in result:
            attendance_date = getdate(row.attendance_date)
            attendance_name = row.name

            checkins = frappe.get_all(
                "Employee Checkin",
                filters={
                    "employee": self.employee,
                    "attendance": attendance_name,
                },
                fields=["*"],
                order_by="time",
            )
            checkin_map.setdefault(attendance_date, []).extend(checkins)
            attendance_doc = frappe.get_doc("Attendance", attendance_name)
            if attendance_doc.docstatus == 1:
                with suppress_incentive_allocation():
                    attendance_doc.cancel()

        start_date = getdate(self.from_date)
        end_date = getdate(self.to_date)

        while start_date <= end_date:
            if start_date > getdate():
                start_date = add_days(start_date, 1)
                continue
            checkins = checkin_map.get(start_date, [])
            with suppress_incentive_allocation():
                create_attendance(self.employee, start_date, checkins)
            # Only submitted requests may drive attendance: a cancelled request
            # cannot be linked at all (CancelledLinkError), and a draft one has
            # not been approved yet. A date can legitimately carry more than one
            # request (overlap validation is disabled), e.g. a First Half and a
            # Second Half request - re-apply every one of them so the day is
            # rebuilt completely.
            attendance_requests = frappe.get_all(
                "Attendance Request",
                filters={
                    "employee": self.employee,
                    "from_date": ["<=", start_date],
                    "to_date": [">=", start_date],
                    "docstatus": 1,
                },
                pluck="name",
                order_by="creation asc",
            )
            for attendance_request in attendance_requests:
                request_doc = frappe.get_doc("Attendance Request", attendance_request)
                with suppress_incentive_allocation():
                    request_doc.create_or_update_attendance(start_date)

            start_date = add_days(start_date, 1)

    def validate_balance_leaves(self):
        if self.from_date and self.to_date:
            self.total_leave_days = get_number_of_leave_days(
                self.employee,
                self.leave_type,
                self.from_date,
                self.to_date,
                self.half_day,
                self.half_day_date,
                custom_half_type=self.custom_half_type,
            )

            if self.total_leave_days <= 0:
                frappe.throw(
                    _(
                        "The day(s) on which you are applying for leave are holidays. You need not apply for leave."
                    )
                )

            if not is_lwp(self.leave_type):
                leave_balance = get_leave_balance_on(
                    self.employee,
                    self.leave_type,
                    self.from_date,
                    self.to_date,
                    consider_all_leaves_in_the_allocation_period=True,
                    for_consumption=True,
                )
                self.leave_balance = leave_balance.get("leave_balance")
                leave_balance_for_consumption = leave_balance.get(
                    "leave_balance_for_consumption"
                )

                if self.status != "Rejected" and (
                    leave_balance_for_consumption < self.total_leave_days
                    or not leave_balance_for_consumption
                ):
                    self.show_insufficient_balance_message(
                        leave_balance_for_consumption
                    )

    def show_insufficient_balance_message(
        self, leave_balance_for_consumption: float
    ) -> None:
        emp_grade = frappe.get_value("Employee", self.employee, "grade")
        advance_leave = frappe.db.get_value(
            "Employee Grade",
            emp_grade,
            [
                "custom_allow_advance_leave",
                "custom_max_no_of_advance_debit",
                "custom_leave_type",
            ],
        )
        is_advance_allowed = advance_leave[0]
        allowed_advance_debit = -abs(advance_leave[1]) or 0
        leave_type = advance_leave[2]
        if frappe.db.get_value("Leave Type", self.leave_type, "allow_negative"):
            if leave_balance_for_consumption != self.leave_balance:
                msg = _(
                    "Warning: Insufficient leave balance for Leave Type {0} in this allocation."
                ).format(frappe.bold(self.leave_type))
                msg += "<br><br>"
                msg += _(
                    "Actual balances aren't available because the leave application spans over different leave allocations. You can still apply for leaves which would be compensated during the next allocation."
                )
            else:
                msg = _(
                    "Warning: Insufficient leave balance for Leave Type {0}."
                ).format(frappe.bold(self.leave_type))

            frappe.msgprint(msg, title=_("Warning"), indicator="orange")
        elif (
            is_advance_allowed
            and allowed_advance_debit
            and leave_type == self.leave_type
        ):
            actual_balance = get_actual_leave_balance_cf(self.employee, self.leave_type)
            if allowed_advance_debit > (actual_balance - self.total_leave_days):
                frappe.throw(
                    _(
                        "Insufficient leave balance for Leave Type {0}, You have reached maximum allowed advance leave"
                    ).format(frappe.bold(self.leave_type)),
                    exc=InsufficientLeaveBalanceError,
                    title=_("Insufficient Balance"),
                )

        else:
            frappe.throw(
                _("Insufficient leave balance for Leave Type {0}").format(
                    frappe.bold(self.leave_type)
                ),
                exc=InsufficientLeaveBalanceError,
                title=_("Insufficient Balance"),
            )

    def validate_attendance(self):
        # Logic is updated based on the half day checking and attendance status
        if getattr(frappe.flags, "in_reprocess_attendance", False):
            return

        if not frappe.db.exists(
            "Attendance",
            {
                "employee": self.employee,
                "attendance_date": ["between", [self.from_date, self.to_date]],
                "docstatus": 1,
            },
        ):
            return

        attendances = frappe.db.sql(
            """select name,attendance_date,status from `tabAttendance` where employee = %s and (attendance_date between %s and %s) and docstatus = 1""",
            (self.employee, self.from_date, self.to_date),
        )
        for att in attendances:
            if getdate(self.from_date) <= att[1] <= getdate(self.to_date):
                if (
                    self.half_day_date
                    and getdate(att[1]) == getdate(self.half_day_date)
                    and att[2] == "Present"
                ):
                    frappe.throw(
                        _(
                            "Attendance for employee {0} is already marked for day: {1}"
                        ).format(self.employee, format_date(att[1])),
                        AttendanceAlreadyMarkedError,
                    )
                elif att[2] == "Present":
                    frappe.throw(
                        _(
                            "Attendance for employee {0} is already marked as Present for day: <br> <ul><li>{1}</li></ul>"
                        ).format(self.employee, format_date(att[1])),
                        AttendanceAlreadyMarkedError,
                    )
                elif att[2] == "Half Day":
                    if not self.half_day_date or getdate(att[1]) != getdate(
                        self.half_day_date
                    ):
                        frappe.throw(
                            _(
                                "Attendance for employee {0} is already marked as Half Day for day: <br> <ul><li>{1}</li></ul>"
                            ).format(self.employee, format_date(att[1])),
                            AttendanceAlreadyMarkedError,
                        )
