"""Safely preserve source-credit links created by the standalone Comp Off app."""

import frappe


def execute():
    """Move the legacy Link value into child-table rows, once per application."""
    if not frappe.db.has_column("Leave Application", "custom_comp_off_source_request"):
        return

    rows = frappe.db.sql(
        """
        SELECT name, custom_comp_off_source_request AS source_request
        FROM `tabLeave Application`
        WHERE custom_comp_off_source_request IS NOT NULL
          AND custom_comp_off_source_request != ''
        """,
        as_dict=True,
    )

    migrated = skipped = 0
    for row in rows:
        if not frappe.db.exists("Compensatory Leave Request", row.source_request):
            skipped += 1
            continue

        exists = frappe.db.exists(
            "Comp Off Source Request",
            {
                "parent": row.name,
                "parenttype": "Leave Application",
                "compensatory_leave_request": row.source_request,
            },
        )
        if exists:
            continue

        child = frappe.get_doc(
            {
                "doctype": "Comp Off Source Request",
                "parent": row.name,
                "parenttype": "Leave Application",
                "parentfield": "custom_comp_off_source_request",
                "idx": frappe.db.count(
                    "Comp Off Source Request", {"parent": row.name, "parenttype": "Leave Application"}
                )
                + 1,
                "compensatory_leave_request": row.source_request,
            }
        )
        child.db_insert()
        migrated += 1

    if migrated or skipped:
        frappe.db.commit()
        frappe.logger("real_group_hrms").info(
            "Comp-Off source migration: migrated %s link(s), skipped %s missing request(s).",
            migrated,
            skipped,
        )
