import frappe


def execute():
    custom_field = "Attendance-custom_reprocess_reference"
    if not frappe.db.exists("Custom Field", custom_field):
        return

    frappe.db.set_value(
        "Custom Field",
        custom_field,
        {
            "fieldtype": "Link",
            "options": "Reprocess Attendance",
        },
        update_modified=False,
    )
    frappe.clear_cache(doctype="Attendance")
