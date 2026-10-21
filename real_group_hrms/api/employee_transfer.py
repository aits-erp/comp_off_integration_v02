import frappe
from frappe.utils import getdate
from hrms.hr.doctype.leave_application.leave_application import (
    get_leave_allocation_records,
)
from hrms.hr.doctype.leave_application.leave_application import get_leave_details as _get_leave_details

from real_group_hrms.utils import get_remaining_days_for_pro_rated


@frappe.whitelist()
def get_leave_details(employee: str):
    data = _get_leave_details(employee, getdate())
    allocation = data.get("leave_allocation")
    if allocation:
        for leave_type, details in allocation.items():
            is_based_on_worked_days, avail_in_next_year = frappe.db.get_value(
                "Leave Type",
                leave_type,
                ["custom_calculate_based_on_working_days", "custom_avail_leave_in_next_calendar_year"],
            )
            if is_based_on_worked_days and not avail_in_next_year:
                allocation = get_leave_allocation_records(employee, getdate(), leave_type)
                from_date = allocation.from_date
                to_date = allocation.to_date
                on_working_days = frappe.db.get_value("Leave Type", leave_type, "custom_number_of_working_days")
                days = get_remaining_days_for_pro_rated(employee, from_date, to_date, on_working_days)
                leaves = days / on_working_days
                adjusted_leaves = adjust_value(leaves)
                details["remaining_leaves"] = details["remaining_leaves"] + adjusted_leaves
    return data


def adjust_value(value: float) -> float:
    """
    Adjusts the value based on custom rounding rules:
    - .01 to .24  -> round down to .0
    - .25 to .74  -> round to .5
    - .75 to .99  -> round up to next integer
    """

    base = int(value)
    frac = value - base

    if 0.01 <= frac <= 0.24:
        return float(base)
    elif 0.25 <= frac <= 0.74:
        return base + 0.5
    elif 0.75 <= frac <= 0.99:
        return float(base + 1)
    else:
        return value
