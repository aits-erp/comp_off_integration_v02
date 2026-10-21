import frappe


def execute():
    names = {
        "Attendance Request": "custom_skip_gate_pass",
        "Leave Application": "custom_skip_gate_pass",
    }
    for doctype, fieldname in names.items():
        frappe.db.delete("Custom Field", {"dt": doctype, "fieldname": fieldname})
