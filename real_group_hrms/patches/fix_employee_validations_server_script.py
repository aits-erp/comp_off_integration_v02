import frappe


EMPLOYEE_VALIDATIONS_SCRIPT = """if " " in (doc.first_name or ""):
    frappe.throw("Spaces not allowed in First Name")

allocation_percentage = 0

for n in (doc.custom_nominee or []):
    allocation_percentage = allocation_percentage + (n.allocation_percentage or 0)

if allocation_percentage != 100:
    frappe.throw("Incorrect Nominee Allocation Percentage, It shoud be 100% only.")

aadhar_number = (doc.custom_aadhar_number or "").strip()

if len(aadhar_number) != 12:
    frappe.throw("Aadhar Number should have 12 digits")

if not aadhar_number.isdigit():
    frappe.throw("Aadhar Number should have only digits")
"""


def execute():
    if frappe.db.exists("Server Script", "Employee Validations"):
        frappe.db.set_value(
            "Server Script",
            "Employee Validations",
            "script",
            EMPLOYEE_VALIDATIONS_SCRIPT,
            update_modified=False,
        )
