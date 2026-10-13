# Copyright (c) 2025, rtCamp and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import get_datetime, get_first_day, get_last_day


class ShortLeave(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        amended_from: DF.Link | None
        branch: DF.Link | None
        company: DF.Link | None
        department: DF.Link | None
        division: DF.Link | None
        employee: DF.Link
        for_date: DF.Date
        punch_time: DF.Datetime
        shift: DF.Link | None
        shift_start_time: DF.Datetime
    # end: auto-generated types
    def validate(self):
        self.validate_short_leave_request()

    def validate_short_leave_request(self):
        grade = frappe.db.get_value("Employee", self.employee, "grade")
        grade = frappe.get_doc("Employee Grade", grade)

        from_date = get_first_day(self.for_date)
        to_date = get_last_day(self.for_date)

        if not (grade.custom_hours_per_leave):
            frappe.throw(frappe._("Not Eligible for short leave, kindly avail Short Leave on Employee Grade"))

        diff = get_datetime(self.punch_time) - get_datetime(self.shift_start_time)
        if grade.custom_hours_per_leave:
            if diff > grade.custom_hours_per_leave:
                frappe.throw(frappe._("Short Leave is not allowed beyond Short Leave Time Allowed "))

        if (
            frappe.db.count(
                "Short Leave",
                {
                    "employee": self.employee,
                    "for_date": ["between", [from_date, to_date]],
                    "docstatus": ["!=", 2],
                    "name": ["!=", self.name],
                },
            )
            + 1
            > grade.custom_number_of_leaves
        ):
            frappe.throw(frappe._("Short Leave Limit Exceeded, Contact your HR Manager"))

    def on_cancel(self):
        self.update_attendance_on_short_leave_cancel()

    def update_attendance_on_short_leave_cancel(self):
        from real_group_hrms.helper.attendance_helper import (
            get_attendance,
            mark_attendance_and_link_log,
            mark_half_day_based_on_deduction_cycle,
            update_time,
        )
        from real_group_hrms.utils import is_holiday_for_employee

        attendance = frappe.db.exists(
            "Attendance",
            {
                "attendance_date": self.for_date,
                "employee": self.employee,
                "docstatus": ["!=", 2],
            },
        )
        if not attendance:
            return

        holiday = is_holiday_for_employee(self.employee, self.for_date)
        emp_grade = frappe.get_value("Employee", self.employee, "grade")
        allowed_late_day, deduction_cycle = frappe.db.get_value(
            "Employee Grade",
            emp_grade,
            ["custom_allowed_late_count_days", "custom_late_entry_deduction_cycle"],
        )
        attendance = frappe.get_doc("Attendance", attendance)
        checkins = frappe.get_all(
            "Employee Checkin",
            filters={
                "employee": self.employee,
                "attendance": attendance.name,
            },
            order_by="time",
            fields=["*"],
        )
        if attendance.docstatus == 1:
            attendance.cancel()
        checkins = update_time(checkins)
        if holiday and not checkins:
            frappe.get_doc(
                {
                    "doctype": "Attendance",
                    "attendance_date": self.for_date,
                    "status": "Present",
                    "custom_attendance_tag": "HO" if not holiday.get("is_weekly_off") else "WO",
                },
            ).insert(ignore_permissions=True)
        else:
            shift = checkins[0].shift

            (
                attendance_status,
                working_hours,
                late_entry,
                early_exit,
                in_time,
                out_time,
            ) = get_attendance(checkins, emp_grade, shift)
            attendance = mark_attendance_and_link_log(
                checkins,
                attendance_status,
                self.for_date,
                working_hours,
                late_entry,
                early_exit,
                in_time,
                out_time,
                shift,
            )
            mark_half_day_based_on_deduction_cycle(self.employee, allowed_late_day, deduction_cycle, attendance)
