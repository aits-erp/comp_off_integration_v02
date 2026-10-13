from datetime import datetime, timedelta

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, format_date, get_time, getdate
from hrms.hr.doctype.attendance_request.attendance_request import AttendanceRequest

from real_group_hrms.helper.attendance_helper import (
    create_attendance,
)
from real_group_hrms.utils import (
    convert_time_to_hours,
    has_absent_attendance,
    holiday_matches_requested_half,
    is_holiday_for_employee,
)


def is_cross_day_shift(shift_name: str | None) -> bool:
    if not shift_name:
        return False

    shift = frappe.db.get_value(
        "Shift Type",
        shift_name,
        ["custom_is_cross_day", "start_time", "end_time"],
        as_dict=True,
    )
    if not shift:
        return False

    if shift.get("custom_is_cross_day"):
        return True

    start_time = shift.get("start_time")
    end_time = shift.get("end_time")
    if not (start_time and end_time):
        return False

    return get_time(start_time) > get_time(end_time)


def get_request_datetime_window(
    from_date,
    to_date,
    from_time,
    to_time,
    shift_name: str | None = None,
) -> tuple[datetime | None, datetime | None]:
    if not (from_date and to_date and from_time and to_time):
        return None, None

    start_dt = datetime.combine(getdate(from_date), get_time(from_time))
    end_dt = datetime.combine(getdate(to_date), get_time(to_time))

    if is_cross_day_shift(shift_name) and end_dt <= start_dt:
        end_dt += timedelta(days=1)

    return start_dt, end_dt


def calculate_request_working_hours(
    from_date,
    to_date,
    from_time,
    to_time,
    shift_name: str | None = None,
) -> float:
    start_dt, end_dt = get_request_datetime_window(
        from_date,
        to_date,
        from_time,
        to_time,
        shift_name,
    )
    if not (start_dt and end_dt):
        return 0.0

    return convert_time_to_hours(end_dt - start_dt)


def calculate_request_working_hours_for_date(
    attendance_date,
    from_time,
    to_time,
    shift_name: str | None = None,
) -> float:
    return calculate_request_working_hours(
        attendance_date,
        attendance_date,
        from_time,
        to_time,
        shift_name,
    )


def get_working_hours_timedelta(hours: float) -> timedelta:
    total_seconds = round(hours * 3600 / 60) * 60
    return timedelta(seconds=total_seconds)


def get_checkins_for_employee_date(employee: str, attendance_date):
    attendance_date = getdate(attendance_date)
    start_dt = datetime.combine(attendance_date, datetime.min.time())
    end_dt = start_dt + timedelta(days=1)

    return frappe.db.sql(
        """
        SELECT *
        FROM `tabEmployee Checkin`
        WHERE employee = %s
          AND (
            (`time` >= %s AND `time` < %s)
            OR (`shift_start` >= %s AND `shift_start` < %s)
          )
        ORDER BY `time`
        """,
        (employee, start_dt, end_dt, start_dt, end_dt),
        as_dict=True,
    )


class AttendanceRequestOverride(AttendanceRequest):
    def validate(self):
        super().validate()
        self.validate_half_type_required()
        self.validate_working_hours_window()

    def validate_half_type_required(self):
        if cint(self.half_day) and not (self.custom_half_type or "").strip():
            frappe.throw(_("Half Type is mandatory when Half Day is selected."))

    def validate_request_overlap(self):
        return  # Overriding the base method to disable overlap validation

    def validate_working_hours_window(self):
        if not (self.custom_from_time and self.custom_to_time and self.from_date and self.to_date):
            return

        working_hours = calculate_request_working_hours_for_date(
            self.from_date,
            self.custom_from_time,
            self.custom_to_time,
            self.shift,
        )
        if working_hours <= 0:
            frappe.throw(
                _(
                    "To Time must be after From Time. Use a cross-day shift or a later To Date for overnight requests."
                )
            )

    def create_or_update_attendance(self, date: str):
        # Attendance links back to this request, so a cancelled (or not yet
        # submitted) request must never reach here - the link would be rejected
        # with CancelledLinkError and roll back the caller's transaction.
        if self.docstatus != 1:
            return

        attendance_name = self.get_attendance_record(date)
        status = self.get_attendance_status(date)
        attendance = None
        if attendance_name:
            old_status = frappe.db.get_value("Attendance", attendance_name, "status")
            existing_leave_type = frappe.db.get_value("Attendance", attendance_name, "leave_type")
            existing_leave_is_lwp = (
                frappe.db.get_value("Leave Type", existing_leave_type, "is_lwp") if existing_leave_type else 0
            )

            if old_status == status and old_status == "Half Day" and status == "Half Day":
                if not existing_leave_is_lwp:
                    status = "Present"
            # Need to create new record, so cancel the existing one
            old_attendance = frappe.get_doc("Attendance", attendance_name)
            old_attendance.cancel()
            attendance = frappe.get_doc("Attendance", attendance_name)

        if attendance:
            doc = frappe.copy_doc(attendance)
        else:
            doc = frappe.new_doc("Attendance")

        doc.update(
            {
                "employee": self.employee,
                "attendance_date": date,
                "shift": self.shift,
                "company": self.company,
                "attendance_request": self.name,
                "status": status,
            }
        )
        doc.insert(ignore_permissions=True)
        doc.submit()

    def get_working_hours(self, attendance_date=None):
        attendance_date = attendance_date or self.from_date
        return calculate_request_working_hours_for_date(
            attendance_date,
            self.custom_from_time,
            self.custom_to_time,
            self.shift,
        )

    def get_working_hours_time(self, hours: float):
        return get_working_hours_timedelta(hours)

    def should_mark_attendance(self, attendance_date: str) -> bool:
        # 1. Check if attendance_date is a holiday or weekly off
        # 2. If it is holiday and not half day, do not mark attendance
        holiday = is_holiday_for_employee(self.employee, attendance_date)
        if holiday and not holiday.get("is_half_day") and not has_absent_attendance(self.employee, attendance_date):
            frappe.msgprint(
                _("Attendance not submitted for {0} as it is a Holiday.").format(
                    frappe.bold(format_date(attendance_date))
                )
            )
            return False
        if holiday_matches_requested_half(holiday, self.custom_half_type) and not has_absent_attendance(
            self.employee, attendance_date
        ):
            frappe.msgprint(
                _("Attendance not submitted for {0} as it falls on the Holiday half.").format(
                    frappe.bold(format_date(attendance_date))
                )
            )
            return False

        # Check if employee is on leave
        if self.has_leave_record(attendance_date):
            frappe.msgprint(
                _("Attendance not submitted for {0} as {1} is on leave.").format(
                    frappe.bold(format_date(attendance_date)), frappe.bold(self.employee)
                )
            )
            return False

        return True

    def has_leave_record(self, attendance_date: str) -> str | None:
        leave = frappe.db.exists(
            "Leave Application",
            {
                "employee": self.employee,
                "docstatus": 1,
                "from_date": ("<=", attendance_date),
                "to_date": (">=", attendance_date),
            },
        )
        if leave:
            leave = frappe.get_doc("Leave Application", leave, for_update=False)
            if leave.half_day and (
                getdate(leave.from_date) == getdate(leave.to_date)
                or getdate(attendance_date) == getdate(leave.half_day_date)
            ):
                return False
        return leave

    @frappe.whitelist()
    def get_attendance_warnings(self) -> list:
        attendance_warnings = []
        request_days = date_diff(self.to_date, self.from_date) + 1

        for day in range(request_days):
            attendance_date = add_days(self.from_date, day)
            holiday = is_holiday_for_employee(self.employee, attendance_date)
            attendance = self.get_attendance_record(attendance_date)

            # Check if attendance_date is a holiday or weekly off.
            # If it is marked Absent already (e.g. sandwich policy), allow overwrite via request.
            if holiday and not holiday.get("is_half_day") and not has_absent_attendance(self.employee, attendance_date):
                attendance_warnings.append({"date": attendance_date, "reason": "Holiday", "action": "Skip"})
            elif holiday_matches_requested_half(holiday, self.custom_half_type) and not has_absent_attendance(
                self.employee, attendance_date
            ):
                attendance_warnings.append({"date": attendance_date, "reason": "Holiday Half", "action": "Skip"})
            elif self.has_leave_record(attendance_date):
                attendance_warnings.append({"date": attendance_date, "reason": "On Leave", "action": "Skip"})
            else:
                if attendance:
                    attendance_warnings.append(
                        {
                            "date": attendance_date,
                            "reason": "Attendance already marked",
                            "record": attendance,
                            "action": "Overwrite",
                        }
                    )

        return attendance_warnings

    # 1. If there is leave application in the attendance then after cancelling attendance, it should be re-created
    # for that leave application. (same goes for half day leave)
    # 2. If attendance is created from the employee checkins, then after cancelling attendance, new attendance should
    # be created from the checkins via. method from attendance_process.
    # 3. If none of the above two conditions are met, then just cancel the attendance as usual and create attendance for
    # Absent.
    def on_cancel(self):
        # When Attendance Requests are cancelled as part of Reprocess Attendance,
        # we don't want to create new Attendance records here (Absent/Leave/etc).
        # Reprocess will handle attendance recreation for the period.
        if getattr(frappe.flags, "in_reprocess_attendance", False):
            return

        from_date = getdate(self.from_date)
        to_date = getdate(self.to_date)

        half_day_date = getdate(self.half_day_date) if self.half_day else None
        while from_date <= to_date:
            day_checkins = get_checkins_for_employee_date(self.employee, from_date)
            other_requests = self.get_other_submitted_requests(from_date)

            # Attendance stores a single `attendance_request` link, so when two
            # half-day requests share a date only the last-submitted one owns it
            # (and the two halves were merged into a full-day "Present"). Look
            # for the day's Attendance under either link, otherwise cancelling
            # one half finds nothing and the merged "Present" survives.
            attendance_name = frappe.db.get_value(
                "Attendance",
                {
                    "employee": self.employee,
                    "attendance_date": from_date,
                    "docstatus": 1,
                    "attendance_request": ("in", [self.name, *other_requests]),
                },
                "name",
            )
            if attendance_name:
                frappe.get_doc("Attendance", attendance_name).cancel()

            # CASE 1: For leave
            leave = frappe.db.get_value(
                "Leave Application",
                {
                    "employee": self.employee,
                    "docstatus": 1,
                    "from_date": ("<=", from_date),
                    "to_date": (">=", from_date),
                },
                ["name", "leave_type", "half_day", "half_day_date", "custom_half_type", "from_date", "to_date"],
                as_dict=True,
            )
            if leave and day_checkins:
                self.create_leave_attendance(leave, from_date, half_day_date, day_checkins)
            elif leave and not day_checkins:
                self.create_leave_attendance(leave, from_date, half_day_date, False)

            # CASE 2: For checkins
            elif day_checkins:
                create_attendance(self.employee, from_date, day_checkins)
            else:
                create_attendance(self.employee, from_date, [])

            # Re-apply the requests that are still approved for this date, so the
            # half they cover is restored on the rebuilt Attendance instead of
            # being lost along with the cancelled one.
            for request_name in other_requests:
                request_doc = frappe.get_doc("Attendance Request", request_name)
                if request_doc.should_mark_attendance(from_date):
                    request_doc.create_or_update_attendance(from_date)

            from_date = add_days(from_date, 1)

    def get_other_submitted_requests(self, date):
        """Still-approved Attendance Requests, other than this one, covering `date`."""
        return frappe.get_all(
            "Attendance Request",
            filters={
                "employee": self.employee,
                "name": ("!=", self.name),
                "docstatus": 1,
                "from_date": ("<=", date),
                "to_date": (">=", date),
            },
            pluck="name",
            order_by="creation asc",
        )

    def create_leave_attendance(self, leave, from_date, half_day_date, has_checkins):
        if leave.half_day:
            if getdate(leave.from_date) == getdate(leave.to_date) or (
                half_day_date and getdate(half_day_date) == from_date
            ):
                doc = frappe.get_doc(
                    {
                        "doctype": "Attendance",
                        "employee": self.employee,
                        "attendance_date": from_date,
                        "status": "Half Day",
                        "custom_half_type": leave.custom_half_type,
                        "company": self.company,
                        "leave_application": leave.name,
                        "leave_type": leave.leave_type,
                    }
                ).insert(ignore_permissions=True)
                doc.submit()
                if has_checkins:
                    # Now process the checkins to create attendance for present half day
                    create_attendance(self.employee, from_date, has_checkins)
        else:
            doc = frappe.get_doc(
                {
                    "doctype": "Attendance",
                    "employee": self.employee,
                    "attendance_date": from_date,
                    "status": "On Leave",
                    "company": self.company,
                    "leave_application": leave.name,
                    "leave_type": leave.leave_type,
                }
            ).insert(ignore_permissions=True)
            doc.submit()
