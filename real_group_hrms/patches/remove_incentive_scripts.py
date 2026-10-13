import frappe


def execute():
    names = [
        "Incentive allocation on Extra Worked Hours",
        "Last Day Incentive allocation on Extra Worked Hours",
        "Incentive if Present on Holiday",
    ]
    frappe.db.delete("Server Script", {"name": ("in", names)})
