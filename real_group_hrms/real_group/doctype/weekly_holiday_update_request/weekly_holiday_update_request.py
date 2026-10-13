# Copyright (c) 2025, rtCamp and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import get_link_to_form, getdate

from real_group_hrms.utils import get_weekly_off

DAY_MAPPING = {
    "Sunday": "SUN",
    "Monday": "MON",
    "Tuesday": "TUE",
    "Wednesday": "WED",
    "Thursday": "THU",
    "Friday": "FRI",
    "Saturday": "SAT",
}


class WeeklyHolidayUpdateRequest(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        amended_from: DF.Link | None
        employee: DF.Link
        name: DF.Int | None
        valid_from: DF.Date
        weekly_off: DF.Link

    # end: auto-generated types
    def on_submit(self):
        if hasattr(self, "flags") and self.flags.ignore_update_employee:
            return
        self.update_weekly_off_in_employee()

    def update_weekly_off_in_employee(self):
        weekly_off = frappe.get_value("Weekly Off List", self.weekly_off, "weekly_off")
        off = DAY_MAPPING.get(weekly_off)
        employee = frappe.get_doc("Employee", self.employee)
        employee.custom_weekly_holiday_list = self.weekly_off
        employee.custom_off_days = off
        employee.save()

    def validate(self):
        self.validate_payroll_date()
        self.validate_date()
        self.validate_back_dated()
        get_weekly_off.clear_cache()

    def validate_date(self):
        date = getdate(self.valid_from)
        exists = frappe.db.exists(
            "Weekly Holiday Update Request",
            {
                "employee": self.employee,
                "valid_from": ("=", date),
                "name": ("!=", self.name),
                "docstatus": 1,
            },
        )
        if exists:
            frappe.throw(
                frappe._("Another {0} exists for this employee with same valid from date.").format(
                    get_link_to_form("Weekly Holiday Update Request", exists, "Weekly Holiday Update Request")
                )
            )

    def validate_back_dated(self):
        date = getdate(self.valid_from)
        data = frappe.db.get_value(
            "Weekly Holiday Update Request",
            {
                "employee": self.employee,
                "docstatus": 1,
            },
            ["name", "valid_from"],
        )
        if not data:
            return
        name, back_date = data
        if back_date and date < getdate(back_date):
            frappe.throw(
                frappe._("Valid From date cannot be before {0} for this employee. As there is existing {1}.").format(
                    back_date, get_link_to_form("Weekly Holiday Update Request", name, "request")
                )
            )

    def validate_payroll_date(self):
        if frappe.db.exists(
            "Salary Slip",
            {
                "employee": self.employee,
                "start_date": ["<=", self.valid_from],
                "end_date": [">=", self.valid_from],
                "docstatus": 1,
            },
        ):
            frappe.throw(frappe._("Cannot process: Salary for this period has already been submitted."))
