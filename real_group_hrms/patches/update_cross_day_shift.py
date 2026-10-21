import frappe
from frappe.utils import cint


def execute():
    shifts = frappe.get_all("Shift Type", pluck="name")

    for shift in shifts:
        doc = frappe.get_doc("Shift Type", shift)
        if hasattr(doc, "custom_end_across_days") and cint(doc.custom_end_across_days) == 1:
            frappe.db.set_value("Shift Type", shift, "custom_is_cross_day", True)

    frappe.db.delete("Custom Field", {"dt": "Shift Type", "fieldname": "custom_end_across_days"})
