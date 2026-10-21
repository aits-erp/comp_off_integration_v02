import frappe
from frappe import _


def validate(doc, method=None):
    validate_completed_event_has_employees(doc)


def validate_completed_event_has_employees(doc):
    if doc.event_status != "Completed":
        return

    if any(row.employee for row in doc.get("employees", [])):
        return

    frappe.throw(_("Employees are mandatory when Event Status is Completed."))
