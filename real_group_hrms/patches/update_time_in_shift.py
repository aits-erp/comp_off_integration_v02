import frappe


def execute():
    shifts = frappe.get_all("Shift Type", pluck="name")

    for shift in shifts:
        shift_doc = frappe.get_doc("Shift Type", shift)
        shift_doc.save()
