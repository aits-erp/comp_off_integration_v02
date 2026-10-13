import frappe


SALARY_STRUCTURE_BEFORE_DELETE_SCRIPT = """ss_list = frappe.db.get_list(
        "Salary Slip",
        {
            'salary_structure': doc.name,
            'docstatus': 1,
        },
        ["name"],
        limit=1
    )
if ss_list:
    frappe.throw(f"Cannot Proceed! Salary Slip {ss_list[0].name} already exists.")
"""


def execute():
    if frappe.db.exists("Server Script", "Salary Structure - Before Delete"):
        frappe.db.set_value(
            "Server Script",
            "Salary Structure - Before Delete",
            "script",
            SALARY_STRUCTURE_BEFORE_DELETE_SCRIPT,
            update_modified=False,
        )
