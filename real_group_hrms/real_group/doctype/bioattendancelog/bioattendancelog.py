# Copyright (c) 2025, rtCamp and contributors
# For license information, please see license.txt


import frappe
from frappe.model.document import Document


class bioattendancelog(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        area: DF.Data | None
        branch: DF.Link | None
        company: DF.Link | None
        department: DF.Link | None
        division: DF.Link | None
        employee_id: DF.Data
        is_processed: DF.Data | None
        message: DF.Text | None
        name: DF.Int | None
        present_day: DF.Data | None
        punch_date: DF.Data | None
        punch_date_backup: DF.Data | None
        punch_direction: DF.Data | None
        punch_time: DF.Data | None
        terminal_id: DF.Data | None
        time_pro_reference_id: DF.Data | None
    # end: auto-generated types
    pass

    def _block(self):
        frappe.throw(
            "bioattendancelog is a system log and cannot be modified",
            frappe.PermissionError,
        )

    def before_insert(self):
        self._block()

    def before_save(self):
        self._block()

    def on_trash(self):
        self._block()


ALLOWED_RESET_ROLES = (
    "HR User",
    "HR Manager",
    "Payroll-CREASX",
    "Payroll-R",
)


@frappe.whitelist()
def reset_bioattendance_logs(log_names):
    frappe.only_for(roles=ALLOWED_RESET_ROLES)

    if not log_names:
        return {"updated": 0}

    if isinstance(log_names, str):
        log_names = frappe.parse_json(log_names)

    names = [name for name in log_names if name]

    if not names:
        return {"updated": 0}

    existing = frappe.get_all("bioattendancelog", filters={"name": ["in", names]}, pluck="name")

    if not existing:
        return {"updated": 0}

    for name in existing:
        frappe.db.set_value("bioattendancelog", name, "is_processed", "N")

    return {"updated": len(existing)}
