"""Compensatory-off source-credit helpers for Leave Applications.

These helpers deliberately operate on the standard HRMS Compensatory Leave
Request and Leave Application doctypes.  They do not allocate, cancel, or
expire credits; those operations remain in the existing attendance and expiry
flows of this app.
"""

import frappe
from frappe.utils import formatdate, getdate


def _get_unused_comp_off_requests(employee, leave_type):
    """Return submitted, unexpired, single-date source credits oldest first."""
    if not employee or not leave_type:
        return []

    if not frappe.db.get_value("Leave Type", leave_type, "is_compensatory"):
        return []

    used_request_names = {
        row.compensatory_leave_request
        for row in frappe.db.sql(
            """
            SELECT source.compensatory_leave_request
            FROM `tabComp Off Source Request` AS source
            INNER JOIN `tabLeave Application` AS application ON application.name = source.parent
            WHERE source.parenttype = 'Leave Application' AND application.docstatus = 1
            """,
            as_dict=True,
        )
    }

    requests = frappe.get_all(
        "Compensatory Leave Request",
        filters={
            "employee": employee,
            "leave_type": leave_type,
            "docstatus": 1,
            "status": ["!=", "Expired"],
        },
        fields=["name", "work_from_date", "work_end_date"],
        order_by="work_from_date asc, creation asc",
    )

    return [
        frappe._dict(name=request.name, work_date=getdate(request.work_from_date))
        for request in requests
        if request.name not in used_request_names
        and getdate(request.work_from_date) == getdate(request.work_end_date)
    ]


@frappe.whitelist()
def get_available_comp_off_requests(doctype, txt, searchfield, start, page_len, filters):
    """Link query for the Comp-Off source-credit multi-select field."""
    filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
    available = _get_unused_comp_off_requests(filters.get("employee"), filters.get("leave_type"))
    results = [
        [request.name, formatdate(request.work_date)]
        for request in available
        if not txt or txt.lower() in request.name.lower()
    ]
    return results[start : start + page_len]


@frappe.whitelist()
def get_available_comp_off_dates(employee, leave_type):
    """Return available credits so the form can give FIFO guidance."""
    return [
        {"name": request.name, "work_date": str(request.work_date)}
        for request in _get_unused_comp_off_requests(employee, leave_type)
    ]
