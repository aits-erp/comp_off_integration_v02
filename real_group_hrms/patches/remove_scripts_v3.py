import frappe


def execute():
    names = [
        "Clear Allowed Shifts Table",
    ]
    frappe.db.delete("Server Script", {"name": ("in", names)})
