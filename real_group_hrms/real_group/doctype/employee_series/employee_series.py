# Copyright (c) 2025, rtCamp and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import get_link_to_form


class EmployeeSeries(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        company: DF.Link
        end: DF.Int
        is_active: DF.Check
        start: DF.Int
    # end: auto-generated types
    pass

    def validate(self):
        self.validate_dates()
        self.validate_overlap()
        self.validate_active_series()

    def validate_dates(self):
        if self.start >= self.end:
            frappe.throw(frappe._("Start value must be less than End value"))

    def validate_overlap(self):
        overlapping_series = frappe.db.get_value(
            "Employee Series",
            {
                "is_active": 1,
                "name": ["!=", self.name],
                "start": ["<=", self.end],
                "end": [">=", self.start],
            },
            fieldname=["name", "company"],
        )
        if overlapping_series:
            frappe.throw(
                frappe._("Overlapping Employee Series found: {0}").format(
                    get_link_to_form(
                        "Employee Series",
                        overlapping_series[0],
                        overlapping_series[1],
                    )
                )
            )

    def validate_active_series(self):
        filters = {"is_active": 1, "company": self.company}
        if not self.is_new():
            filters["name"] = ["!=", self.name]
        exists = frappe.db.exists("Employee Series", filters)
        if exists:
            frappe.throw(
                frappe._(
                    "An active Employee Series already exists for this company: {0}. Please deactivate it before activating a new one."
                ).format(get_link_to_form("Employee Series", exists, self.company))
            )
