import frappe


def execute():
    names = [
        "Reprocess Attendance-custom_state",
    ]
    frappe.db.delete("Custom Field", {"name": ("in", names)})
