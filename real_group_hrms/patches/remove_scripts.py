import frappe


def execute():
    names = [
        "Comp-off on Extra Worked Hours",
        "Setting up Identifier Shift Type",
        "Comp off on Present on holiday",
        "Comp-off and Incentive allocation on Extra Worked Hours",
        "Terminate Comp Off",
    ]
    frappe.db.delete("Server Script", {"name": ("in", names)})
