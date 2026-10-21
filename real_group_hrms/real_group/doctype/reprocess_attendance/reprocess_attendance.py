# Copyright (c) 2024, Step Tech and contributors
# For license information, please see license.txt


import frappe
from frappe.model.document import Document
from frappe.model.workflow import get_workflow_state_field
from frappe.utils import add_days, date_diff, get_datetime, get_link_to_form, getdate

from real_group_hrms.api.overrides.leave_application import get_leave_balance_on
from real_group_hrms.doc_events.attendance import (
    allocate_c_off,
    allocate_incentive,
    is_absence_side_status,
    revert_sandwich_attendance,
    sandwich_attendance,
)
from real_group_hrms.tasks.process_attendance import process as _process_attendance
from real_group_hrms.utils import is_holiday_for_employee


class ReprocessAttendance(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        amended_from: DF.Link | None
        branch: DF.Link
        company: DF.Link
        department: DF.Link | None
        division: DF.Link | None
        employee: DF.Link
        from_date: DF.Date
        reprocess_attendance_bulk: DF.Link | None
        status: DF.Literal["Draft", "In Progress", "Completed", "Error"]
        to_date: DF.Date
    # end: auto-generated types

    def validate(self):
        self.validate_dates()
        self.validate_allowed_days()
        self.validate_salary_slip(*self.get_dates())

    def before_submit(self):
        self.validate_pending_attendance()
        from_date, to_date = self.get_dates()
        self.validate_salary_slip(from_date, to_date)

    def on_submit(self):
        if hasattr(self.flags, "from_bulk") and self.flags.from_bulk:
            return
        frappe.enqueue_doc(
            self.doctype,
            self.name,
            "run_process",
            queue="long",
            timeout=60 * 60,
            enqueue_after_commit=True,
        )

    def run_process(self):
        frappe.flags.reprocess_attendance_reference = self.name
        try:
            self.process_removal()
            self.reprocess()
        finally:
            frappe.flags.reprocess_attendance_reference = None

    def get_leave_applications(self, from_date, to_date):
        leave_applications = frappe.get_all(
            "Leave Application",
            filters={
                "employee": self.employee,
                "from_date": ["between", [from_date, to_date]],
                "to_date": ["between", [from_date, to_date]],
                "docstatus": 1,
            },
            pluck="name",
        )
        return leave_applications

    def get_requests(self, from_date, to_date):
        attendance_requests = frappe.get_all(
            "Attendance Request",
            filters={
                "employee": self.employee,
                "from_date": ["between", [from_date, to_date]],
                "to_date": ["between", [from_date, to_date]],
                "docstatus": 1,
            },
            pluck="name",
        )
        return attendance_requests

    def validate_pending_attendance(self):
        pending_attendance = frappe.get_all(
            "Reprocess Attendance",
            filters={
                "employee": self.employee,
                "from_date": ["<=", self.to_date],
                "to_date": [">=", self.from_date],
                "docstatus": ["!=", 2],
                "status": "In Progress",
                "name": ["!=", self.name],
            },
            pluck="name",
        )
        if pending_attendance:
            frappe.throw(
                frappe._(
                    "There is already a pending Reprocess Attendance {0} for the selected employee and date range."
                ).format(
                    ", ".join(
                        [
                            get_link_to_form("Reprocess Attendance", pa)
                            for pa in pending_attendance
                        ]
                    )
                )
            )

    def validate_dates(self):
        from_date, to_date = self.get_dates()
        if from_date > to_date:
            frappe.throw(frappe._("From Date cannot be greater than To Date"))
        if to_date > getdate():
            frappe.throw(frappe._("To Date cannot be greater than today's date"))

    def validate_allowed_days(self):
        _, to_date = self.get_dates()
        day_diff = date_diff(getdate(), to_date)
        if day_diff < 1:
            frappe.throw(
                frappe._("To Date must be at least 1 day before today's date")
            )

    def validate_leave_application(self):
        leave_requests = frappe.get_all(
            "Leave Application",
            filters={
                "employee": self.employee,
                "from_date": ["<=", self.to_date],
                "to_date": [">=", self.from_date],
                "docstatus": 0,
                "workflow_state": ["in", ["Draft", "Pending at HOD", "Pending at HR"]],
            },
            pluck="name",
        )
        if leave_requests:
            frappe.throw(
                frappe._(
                    "Leave Requests {0} exist for the selected date range. Please resolve them before proceeding."
                ).format(
                    ", ".join(
                        [
                            get_link_to_form("Leave Application", lr)
                            for lr in leave_requests
                        ]
                    )
                )
            )

    def validate_attendance_request(self):
        attendance_requests = frappe.get_all(
            "Attendance Request",
            filters={
                "employee": self.employee,
                "from_date": ["<=", self.to_date],
                "to_date": [">=", self.from_date],
                "docstatus": 0,
                "workflow_state": [
                    "in",
                    ["Draft", "Pending at HOD", "Gate Pass", "Pending at HR"],
                ],
            },
            pluck="name",
        )
        if attendance_requests:
            frappe.throw(
                frappe._(
                    "Attendance Requests {0} exist for the selected date range. Please resolve them before proceeding."
                ).format(
                    ", ".join(
                        [
                            get_link_to_form("Attendance Request", ar)
                            for ar in attendance_requests
                        ]
                    )
                )
            )

    def get_dates(self):
        return getdate(self.from_date), getdate(self.to_date)

    def validate_salary_slip(self, from_date, to_date):
        salary_exists = frappe.db.exists(
            "Salary Slip",
            {
                "employee": self.employee,
                "start_date": ["<=", from_date],
                "end_date": [">=", to_date],
                "docstatus": ["!=", 2],
            },
        )
        if salary_exists:
            frappe.throw(
                frappe._("Salary Slip(s) exist for the selected period: {0}").format(
                    get_link_to_form("Salary Slip", salary_exists)
                )
            )

    def get_link_to_self(self):
        return get_link_to_form("Reprocess Attendance", self.name)

    def process_removal(self):
        frappe.flags.in_reprocess_attendance = True
        self.db_set("status", "In Progress")
        from_date, to_date = self.get_dates()
        self.cancel_leaves(from_date, to_date)
        self.cancel_attendance_requests(from_date, to_date)
        self.cancel_attendance(from_date, to_date)
        # frappe.db.commit()  # nosemgrep

    def reprocess(self):
        frappe.flags.in_reprocess_attendance = True
        from_date, to_date = self.get_dates()
        employee_grade = frappe.db.get_value("Employee", self.employee, "grade")
        grade = frappe.get_doc("Employee Grade", employee_grade, for_update=False)
        if grade.custom_no_punch_applicable:
            self.process_for_no_checkins(from_date, to_date)
        elif grade.custom_single_punch_applicable:
            self.process_single_checkins(from_date, to_date)
        else:
            self.process_attendance(from_date, to_date)
        self.db_set("status", "Completed")

    def process_for_no_checkins(self, from_date, to_date):
        start_date = from_date
        if getdate(to_date) > getdate():
            end_date = getdate()
        else:
            end_date = getdate(to_date)

        while start_date <= end_date:
            attendance = frappe.get_doc(
                {
                    "naming_series": "HR-ATT-.YYYY.-",
                    "doctype": "Attendance",
                    "employee": self.employee,
                    "status": "Present",
                    "attendance_date": start_date,
                    "company": self.company,
                    "custom_reprocess_reference": self.name,
                    "custom_attendance_tag": "P",
                }
            )
            attendance.save()
            attendance.add_tag("No Check in Required")
            attendance.submit()
            # frappe.db.commit()  # nosemgrep
            start_date = add_days(start_date, 1)

        self.process_leave_and_requests(from_date, to_date)

    def process_single_checkins(self, from_date, to_date):
        start_date = from_date
        end_date = to_date

        while start_date <= end_date:
            start_time = get_datetime(add_days(start_date, -1))
            end_time = get_datetime(add_days(start_date, 1))
            holiday = is_holiday_for_employee(self.employee, start_date)
            filters = [
                ["employee", "=", self.employee],
                ["shift_start", ">=", start_time],
                ["shift_end", "<", end_time],
                ["attendance", "is", "not set"],
            ]
            checkins = frappe.get_all(
                "Employee Checkin", filters=filters, fields=["name", "shift_start", "log_type"], order_by="shift_start asc"
            )
            emp_checkin = len(checkins)
            has_valid_in_out = any(c.get("log_type") == "IN" for c in checkins) and any(
                c.get("log_type") == "OUT" for c in checkins
            )
            if holiday and has_valid_in_out:
                attendance = frappe.get_doc(
                    {
                        "doctype": "Attendance",
                        "employee": self.employee,
                        "attendance_date": start_date,
                        "status": "Present",
                        "custom_attendance_tag": "POW" if holiday.get("is_weekly_off") else "POH",
                        "custom_reprocess_reference": self.name,
                    }
                )
                attendance.insert(ignore_permissions=True)
                attendance.submit()
            elif holiday:
                attendance = frappe.get_doc(
                    {
                        "doctype": "Attendance",
                        "employee": self.employee,
                        "attendance_date": start_date,
                        "status": "Present",
                        "custom_attendance_tag": (
                            "HO" if not holiday.get("is_weekly_off") else "WO"
                        ),
                        "custom_reprocess_reference": self.name,
                    }
                )
                attendance.insert(ignore_permissions=True)
                attendance.submit()
            else:
                if not emp_checkin or emp_checkin == 0:
                    attendance = frappe.get_doc(
                        {
                            "doctype": "Attendance",
                            "employee": self.employee,
                            "attendance_date": start_date,
                            "status": "Absent",
                            "custom_attendance_tag": "A",
                            "custom_reprocess_reference": self.name,
                        }
                    )
                    attendance.insert(ignore_permissions=True)
                    attendance.submit()

                else:
                    shift_date = getdate(checkins[0].get("shift_start")) if checkins[0].get("shift_start") else start_date
                    attendance = frappe.get_doc(
                        {
                            "doctype": "Attendance",
                            "employee": self.employee,
                            "attendance_date": shift_date,
                            "status": "Present",
                            "custom_attendance_tag": "P",
                            "custom_reprocess_reference": self.name,
                        }
                    )
                    attendance.insert(ignore_permissions=True)
                    attendance.submit()
                    for checkin in checkins:
                        frappe.db.set_value(
                            "Employee Checkin", checkin.get("name"), "attendance", attendance.name
                        )
            attendance.add_tag("Single Check in Required")
            # frappe.db.commit()  # nosemgrep
            start_date = add_days(start_date, 1)
        self.process_leave_and_requests(from_date, to_date)

    def process_attendance(self, from_date, to_date):
        start_date = from_date
        end_date = to_date

        while start_date <= add_days(end_date, 1):
            try:
                frappe.flags.in_reprocess_attendance = True
                _process_attendance(
                    from_date=start_date,
                    employee_names=[self.employee],
                    reprocess_ref=self.name,
                )
            except Exception:
                frappe.log_error(
                    frappe.get_traceback(),
                    f"Error in Reprocess Attendance: {self.name} for date {start_date}",
                )
            start_date = add_days(start_date, 1)

        self.process_leave_and_requests(from_date, to_date)

    def process_leave_and_requests(self, from_date, to_date):
        self.apply_attendance_requests()
        self.apply_leave_applications()
        # frappe.db.commit()  # nosemgrep

        attendances = frappe.get_all(
            "Attendance",
            filters={
                "employee": self.employee,
                "attendance_date": ["between", [from_date, to_date]],
                "custom_reprocess_reference": self.name,
                "docstatus": 1,
            },
            pluck="name",
        )
        for attendance in attendances:
            doc = frappe.get_doc("Attendance", attendance)
            allocate_c_off(doc)
            allocate_incentive(doc)
            if is_absence_side_status(
                doc.status, doc.leave_application, doc.attendance_request
            ):
                sandwich_attendance(doc)
            else:
                revert_sandwich_attendance(doc)
            # frappe.db.commit()  # nosemgrep

    def apply_attendance_requests(self):
        requests = self.get_cancelled_requests()
        for request in requests:
            try:
                doc = frappe.get_doc("Attendance Request", request)
                start_date = getdate(doc.from_date)
                end_date = getdate(doc.to_date)
                half_day_date = (
                    getdate(doc.half_day_date) if doc.half_day_date else None
                )
                while start_date <= end_date:
                    try:
                        frappe.flags.in_install = "frappe"
                        new_request = frappe.copy_doc(doc)
                        new_request.from_date = start_date
                        new_request.to_date = start_date
                        if doc.half_day:
                            new_request.half_day = 1
                            if (half_day_date == start_date) or (
                                doc.from_date == doc.to_date
                            ):
                                new_request.half_day_date = start_date
                        else:
                            new_request.half_day = 0
                            new_request.half_day_date = None
                        new_request.status = "Approved"
                        workflow_name = new_request.meta.get_workflow()
                        field_name = get_workflow_state_field(workflow_name)
                        new_request.update({field_name: "Approved"})
                        new_request.name = None
                        new_request.insert(ignore_permissions=True)
                        new_request.submit()
                    except Exception:
                        frappe.log_error(
                            frappe.get_traceback(),
                            f"Error in Reprocess Attendance : {self.name}",
                        )
                    start_date = add_days(start_date, 1)
            except Exception:
                frappe.log_error(
                    frappe.get_traceback(),
                    f"Error in Reprocess Attendance : {self.name}",
                )
        frappe.cache.hdel("reprocess-attendance-cancelled-requests", self.name)

    def apply_leave_applications(
        self,
    ):
        leave_applications = self.get_cancelled_leaves()
        for application in leave_applications:
            try:
                doc = frappe.get_doc("Leave Application", application)
                try:
                    frappe.flags.in_install = "frappe"  # Hack to bypass the workflow

                    # Recreate the leave exactly as it was (same from/to range).
                    # Splitting into per-day leaves breaks weekly-offs/holidays inside the range
                    # and can create overlapping Leave Applications.
                    new_leave = frappe.copy_doc(doc)
                    new_leave.from_date = doc.from_date
                    new_leave.to_date = doc.to_date

                    leave_type = doc.leave_type
                    is_lwp = frappe.db.get_value("Leave Type", leave_type, "is_lwp")
                    has_leave_balance = 0 if is_lwp else self.get_leave_type_balance(leave_type)
                    if is_lwp or (has_leave_balance and has_leave_balance > 0):
                        new_leave.status = "Approved"
                        workflow_name = new_leave.meta.get_workflow()
                        field_name = get_workflow_state_field(workflow_name)
                        new_leave.update({field_name: "Approved"})
                        new_leave.name = None
                        new_leave.insert(ignore_permissions=True)
                        new_leave.submit()
                except Exception:
                    frappe.log_error(
                        frappe.get_traceback(),
                        f"Error in Reprocess Attendance : {self.name}",
                    )
            except Exception:
                frappe.log_error(
                    frappe.get_traceback(),
                    f"Error in Reprocess Attendance: {self.name}",
                )
        frappe.cache.hdel("reprocess-attendance-cancelled-leaves", self.name)

    def cancel_leaves(self, from_date, to_date):
        leave_names = []
        leaves = frappe.get_all(
            "Leave Application",
            filters={
                "employee": self.employee,
                "from_date": ["<=", to_date],
                "to_date": [">=", from_date],
                "docstatus": 1,
            },
            pluck="name",
        )
        for leave in leaves:
            doc = frappe.get_doc("Leave Application", leave)
            doc.flags.ignore_links = True
            doc.cancel()
            doc.add_comment(
                comment_type="Comment",
                text=frappe._(
                    "Cancelled by Reprocess Attendance {0}".format(
                        self.get_link_to_self()
                    )
                ),
            )
            workflow_name = doc.meta.get_workflow()
            field_name = get_workflow_state_field(workflow_name)
            if field_name:
                doc.db_set(field_name, "Cancelled")
            leave_names.append(leave)

        frappe.cache.hset(
            "reprocess-attendance-cancelled-leaves", self.name, leave_names
        )

    def cancel_attendance_requests(self, from_date, to_date):
        request_names = []
        requests = self.get_requests(from_date, to_date)
        for request in requests:
            doc = frappe.get_doc("Attendance Request", request)
            doc.flags.ignore_links = True
            doc.cancel()
            doc.add_comment(
                comment_type="Comment",
                text=frappe._(
                    "Cancelled by Reprocess Attendance {0}".format(
                        self.get_link_to_self()
                    )
                ),
            )
            workflow_name = doc.meta.get_workflow()
            field_name = get_workflow_state_field(workflow_name)
            if field_name:
                doc.db_set(field_name, "Cancelled")
            request_names.append(request)

        frappe.cache.hset(
            "reprocess-attendance-cancelled-requests", self.name, request_names
        )

    def get_cancelled_requests(self):
        requests = frappe.cache.hget(
            "reprocess-attendance-cancelled-requests", self.name
        )
        return requests

    def get_cancelled_leaves(self):
        leaves = frappe.cache.hget("reprocess-attendance-cancelled-leaves", self.name)
        return leaves

    def cancel_attendance(self, from_date=None, to_date=None):
        attendances = frappe.get_all(
            "Attendance",
            filters={
                "employee": self.employee,
                "attendance_date": ["between", [from_date, to_date]],
                "docstatus": 1,
            },
            pluck="name",
        )

        for attendance in attendances:
            doc = frappe.get_doc("Attendance", attendance)
            doc.db_set("custom_reprocess_reference", self.name)
            doc.cancel()
            doc.add_comment(
                comment_type="Comment",
                text=frappe._(
                    "Cancelled by Reprocess Attendance {0}".format(
                        self.get_link_to_self()
                    )
                ),
            )

    def get_leave_type_balance(self, leave_type):
        balance = get_leave_balance_on(
            employee=self.employee,
            leave_type=leave_type,
            date=getdate(),
            consider_all_leaves_in_the_allocation_period=True,
            for_consumption=True,
        )
        return balance.get("leave_balance_for_consumption", 0.0)
