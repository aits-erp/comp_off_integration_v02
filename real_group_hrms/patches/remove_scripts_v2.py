import frappe


def execute():
    names = [
        "Compensation Matrix Validation",
    ]
    frappe.db.delete("Server Script", {"name": ("in", names)})
