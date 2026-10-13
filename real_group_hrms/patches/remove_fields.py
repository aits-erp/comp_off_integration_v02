import frappe


def execute():
    names = [
        "Employee-custom_posting_location",
    ]
    frappe.db.delete("Custom Field", {"name": ("in", names)})
