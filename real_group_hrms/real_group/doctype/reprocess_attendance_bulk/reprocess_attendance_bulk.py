# Copyright (c) 2024, Step Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import date_diff, get_link_to_form, getdate


class ReprocessAttendanceBulk(Document):
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
        from_date: DF.Date
        to_date: DF.Date
    # end: auto-generated types

    def validate(self):
        self.validate_dates()
        self.validate_allowed_days()

    def before_submit(self):
        self.validate_in_progress_attendance()
        self.validate_salary_slip()

    def on_submit(self):
        frappe.enqueue_doc(
            self.doctype, self.name, method="process", queue="long", timeout=7200, enqueue_after_commit=True
        )

    def process(self):
        frappe.db.sql("SET SESSION innodb_lock_wait_timeout = 120")
        data = self.get_reprocess_attendance()
        for d in data:
            try:
                reprocess_attendance = frappe.get_doc("Reprocess Attendance", d)
                reprocess_attendance.flags.from_bulk = True
                reprocess_attendance.submit()
                reprocess_attendance.run_process()
                frappe.db.commit()
            except Exception:
                frappe.log_error(
                    title=f"Error processing Reprocess Attendance {d} from Reprocess Attendance Bulk {self.name}",
                    message=frappe.get_traceback(),
                )
                continue

    def get_reprocess_attendance(self):
        return frappe.get_all(
            "Reprocess Attendance",
            filters={"reprocess_attendance_bulk": self.name},
            pluck="name",
        )

    def validate_in_progress_attendance(self):
        employees = self.get_employees()
        in_progress_attendance = frappe.get_all(
            "Reprocess Attendance",
            filters={
                "employee": ["in", employees],
                "from_date": ["<=", self.to_date],
                "to_date": [">=", self.from_date],
                "docstatus": ["!=", 2],
                "status": "In Progress",
            },
            pluck="name",
        )
        if in_progress_attendance:
            frappe.throw(
                frappe._(
                    "Reprocess Attendance records {0} are still in progress for the selected employees and date range. Please resolve them before proceeding."
                ).format(", ".join([get_link_to_form("Reprocess Attendance", ra) for ra in in_progress_attendance]))
            )

    def validate_leave_application(self):
        employees = self.get_employees()
        leave_requests = frappe.get_all(
            "Leave Application",
            filters={
                "employee": ["in", employees],
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
                    "Leave Requests {0} exist for the selected employees and date range. Please resolve them before proceeding."
                ).format(", ".join([get_link_to_form("Leave Application", lr) for lr in leave_requests]))
            )

    def validate_attendance_request(self):
        employees = self.get_employees()
        attendance_requests = frappe.get_all(
            "Attendance Request",
            filters={
                "employee": ["in", employees],
                "from_date": ["<=", self.to_date],
                "to_date": [">=", self.from_date],
                "docstatus": 0,
                "workflow_state": ["in", ["Draft", "Pending at HOD", "Gate Pass", "Pending at HR"]],
            },
            pluck="name",
        )
        if attendance_requests:
            frappe.throw(
                frappe._(
                    "Attendance Requests {0} exist for the selected employees and date range. Please resolve them before proceeding."
                ).format(", ".join([get_link_to_form("Attendance Request", ar) for ar in attendance_requests]))
            )

    def validate_dates(self):
        from_date = getdate(self.from_date)
        to_date = getdate(self.to_date)
        if from_date > to_date:
            frappe.throw(frappe._("From Date cannot be greater than To Date"))
        if to_date > getdate():
            frappe.throw(frappe._("To Date cannot be greater than today's date"))

    def validate_allowed_days(self):
        _, to_date = self.get_dates()
        day_diff = date_diff(getdate(), to_date)
        if day_diff < 1:
            frappe.throw(frappe._("To Date must be at least 1 day before today's date"))

    def after_insert(self):
        self.create_reprocess_attendance()

    def validate_salary_slip(self):
        from_date, to_date = self.get_dates()
        employees = self.get_employees()
        salary_slips = frappe.get_all(
            "Salary Slip",
            {
                "employee": ["in", employees],
                "start_date": ["<=", from_date],
                "end_date": [">=", to_date],
                "docstatus": ["!=", 2],
            },
            pluck="name",
        )
        if salary_slips:
            frappe.throw(
                frappe._("Salary Slip(s) exist for the selected period: {0}").format(
                    ", ".join([get_link_to_form("Salary Slip", ss) for ss in salary_slips])
                )
            )

    def create_reprocess_attendance(self):
        employees = self.get_employees()
        for emp in employees:
            reprocess_attendance = frappe.get_doc(
                dict(
                    doctype="Reprocess Attendance",
                    company=self.company,
                    branch=self.branch,
                    division=self.division,
                    department=self.department,
                    from_date=self.from_date,
                    to_date=self.to_date,
                    reprocess_attendance_bulk=self.name,
                    employee=emp,
                )
            )
            reprocess_attendance.save()

    def get_employees(self):
        filters = {"status": "Active"}
        if self.company:
            filters["company"] = self.company
        if self.branch:
            filters["branch"] = self.branch
        if self.division:
            filters["custom_division"] = self.division
        if self.department:
            filters["department"] = self.department
        return frappe.get_all("Employee", filters=filters, pluck="name")

    def get_dates(self):
        return getdate(self.from_date), getdate(self.to_date)
