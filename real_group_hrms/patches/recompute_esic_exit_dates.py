import frappe
from frappe.utils import getdate

from real_group_hrms.doc_events.salary_structure_assignment import get_esic_exit_date_for_assignment


def execute():
    assignments = frappe.get_all(
        "Salary Structure Assignment",
        filters={"docstatus": 1},
        fields=["name"],
        order_by="employee asc, from_date asc, creation asc",
    )

    for assignment in assignments:
        doc = frappe.get_doc("Salary Structure Assignment", assignment.name)
        expected_exit_date = get_esic_exit_date_for_assignment(doc)
        current_exit_date = getdate(doc.custom_esi_exit_date) if doc.custom_esi_exit_date else None

        if current_exit_date == expected_exit_date:
            continue

        frappe.db.set_value(
            "Salary Structure Assignment",
            doc.name,
            "custom_esi_exit_date",
            expected_exit_date,
            update_modified=False,
        )
