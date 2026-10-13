import datetime

import frappe
from frappe.query_builder.functions import Sum
from frappe.utils import add_days, cint, date_diff, flt, getdate, nowdate
from hrms.hr.doctype.leave_application.leave_application import (
    get_allocation_expiry_for_cf_leaves,
    get_leave_details as _get_leave_details,
    get_leave_allocation_records,
    get_leaves_for_period,
    get_new_and_cf_leaves_taken,
)
from hrms.hr.doctype.leave_application.leave_application import (
    get_holidays as _get_holidays,
)

from real_group_hrms.utils import holiday_matches_requested_half, is_holiday_for_employee


@frappe.whitelist()
def get_holidays(employee, from_date, to_date, holiday_list=None):
    holidays = _get_holidays(employee, from_date, to_date, holiday_list)

    weekly_holiday_list = frappe.db.get_value(
        "Employee", employee, "custom_weekly_holiday_list"
    )

    weekly_holidays = frappe.db.count(
        "Weekly Off Holiday",
        {
            "parent": weekly_holiday_list,
            "holiday_date": ["between", [from_date, to_date]],
        },
    )
    return holidays + weekly_holidays


@frappe.whitelist()
def get_leave_details(employee, date):
    leave_details = _get_leave_details(employee, getdate(date))
    leave_allocation = leave_details.get("leave_allocation") or {}

    for details in leave_allocation.values():
        # Keep displayed available balance equal to actual earned balance.
        # Pending requests are already exposed separately via leaves_pending_approval.
        details["available_leaves"] = flt(details.get("remaining_leaves"))

    return leave_details


@frappe.whitelist()
def get_number_of_leave_days(
    employee: str,
    leave_type: str,
    from_date: datetime.date,
    to_date: datetime.date,
    half_day: int | str | None = None,
    half_day_date: datetime.date | str | None = None,
    holiday_list: str | None = None,
    custom_half_type: str | None = None,
) -> float:
    """
    Return number of leave days considering:
      - half days
      - full-day or half-day holidays
      - sandwich leave logic (only if enabled in Employee Grade)

    Rules:
    - With sandwich enabled, every day in the selected range is counted.
    - Full holidays / weekly offs count as 1 day when sandwich is enabled.
    - Half-day holidays count as 0.5 day.
    - Without sandwich, full holidays / weekly offs are excluded.
    """

    from_date = getdate(from_date)
    to_date = getdate(to_date)
    half_day_date = getdate(half_day_date) if half_day_date else None
    is_half_day = cint(half_day) == 1

    grade = frappe.db.get_value("Employee", employee, "grade")
    apply_sandwich = False
    if grade:
        apply_sandwich = (
            frappe.db.get_value("Employee Grade", grade, "custom_sandwich_flag") == 1
        )

    total = 0.0
    current = from_date
    while current <= to_date:
        holiday_info = is_holiday_for_employee(employee, current) or {}

        if is_half_day and half_day_date == current:
            if not holiday_matches_requested_half(holiday_info, custom_half_type):
                total += 0.5
            current = add_days(current, 1)
            continue

        if holiday_info.get("is_holiday"):
            if holiday_info.get("is_half_day"):
                total += 0.5
            elif apply_sandwich:
                total += 1
        else:
            total += 1

        current = add_days(current, 1)

    return flt(total)


# Taken from upstream, since existing method does not handle manually expired allocations
@frappe.whitelist()
def get_leave_balance_on(
    employee: str,
    leave_type: str,
    date: datetime.date,
    to_date: datetime.date | None = None,
    consider_all_leaves_in_the_allocation_period: bool = False,
    for_consumption: bool = False,
):
    """
    Returns leave balance till date
    :param employee: employee name
    :param leave_type: leave type
    :param date: date to check balance on
    :param to_date: future date to check for allocation expiry
    :param consider_all_leaves_in_the_allocation_period: consider all leaves taken till the allocation end date
    :param for_consumption: flag to check if leave balance is required for consumption or display
            eg: employee has leave balance = 10 but allocation is expiring in 1 day so employee can only consume 1 leave
            in this case leave_balance = 10 but leave_balance_for_consumption = 1
            if True, returns a dict eg: {'leave_balance': 10, 'leave_balance_for_consumption': 1}
            else, returns leave_balance (in this case 10)
    """

    if not to_date:
        to_date = nowdate()

    allocation_records = get_leave_allocation_records(employee, date, leave_type)
    allocation = allocation_records.get(leave_type, frappe._dict())

    if not allocation:
        empty_balance = frappe._dict(
            leave_balance=0.0, leave_balance_for_consumption=0.0
        )
        return empty_balance if for_consumption else 0.0

    end_date = (
        allocation.to_date
        if cint(consider_all_leaves_in_the_allocation_period)
        else date
    )
    cf_expiry = get_allocation_expiry_for_cf_leaves(
        employee, leave_type, to_date, allocation.from_date
    )

    leaves_taken = get_leaves_for_period(
        employee, leave_type, allocation.from_date, end_date
    )

    # Only count manual expiry entries up to the balance reference date.
    manually_expired_leaves = get_manually_expired_leaves(
        employee, leave_type, allocation.from_date, date
    )

    remaining_leaves = get_remaining_leaves(
        allocation, leaves_taken, date, cf_expiry, manually_expired_leaves
    )

    if for_consumption:
        return remaining_leaves
    else:
        return remaining_leaves.get("leave_balance")


def get_remaining_leaves(
    allocation: dict,
    leaves_taken: float,
    date: str,
    cf_expiry: str,
    manually_expired_leaves: float,
) -> dict[str, float]:
    """Returns a dict of leave_balance and leave_balance_for_consumption
    leave_balance returns the available leave balance
    leave_balance_for_consumption returns the minimum leaves remaining after comparing with remaining days for allocation expiry
    """

    def _get_remaining_leaves(remaining_leaves, end_date):
        """Returns minimum leaves remaining after comparing with remaining days for allocation expiry"""
        if remaining_leaves > 0:
            remaining_days = date_diff(end_date, date) + 1
            remaining_leaves = min(remaining_days, remaining_leaves)

        return remaining_leaves

    if cf_expiry and allocation.unused_leaves:
        # allocation contains both carry forwarded and new leaves
        new_leaves_taken, cf_leaves_taken = get_new_and_cf_leaves_taken(
            allocation, cf_expiry
        )

        if getdate(date) > getdate(cf_expiry):
            # carry forwarded leaves have expired
            cf_leaves = remaining_cf_leaves = 0
        else:
            cf_leaves = flt(allocation.unused_leaves) + flt(cf_leaves_taken)
            remaining_cf_leaves = _get_remaining_leaves(cf_leaves, cf_expiry)

        # new leaves allocated - new leaves taken + cf leave balance
        # Note: `new_leaves_taken` is added here because its already a -ve number in the ledger
        leave_balance = (
            (flt(allocation.new_leaves_allocated) + flt(new_leaves_taken))
            + flt(cf_leaves)
            + flt(manually_expired_leaves)
        )
        leave_balance_for_consumption = (
            (flt(allocation.new_leaves_allocated) + flt(new_leaves_taken))
            + flt(remaining_cf_leaves)
            + flt(manually_expired_leaves)
        )
    else:
        # allocation only contains newly allocated leaves
        leave_balance = leave_balance_for_consumption = (
            flt(allocation.total_leaves_allocated)
            + flt(leaves_taken)
            + flt(manually_expired_leaves)
        )

    remaining_leaves = _get_remaining_leaves(
        leave_balance_for_consumption, allocation.to_date
    )
    return frappe._dict(
        leave_balance=leave_balance, leave_balance_for_consumption=remaining_leaves
    )


def get_manually_expired_leaves(
    employee: str, leave_type: str, from_date: datetime.date, end_date: datetime.date
):
    ledger = frappe.qb.DocType("Leave Ledger Entry")
    allocation = frappe.qb.DocType("Leave Allocation")

    if not (from_date and end_date):
        return 0.0

    from_date = getdate(from_date)
    end_date = getdate(end_date)

    leaves = (
        frappe.qb.from_(ledger)
        .inner_join(allocation)
        .on(ledger.transaction_name == allocation.name)
        .select(Sum(ledger.leaves).as_("expired_leaves"))
        .where(
            (ledger.docstatus == 1)
            & (ledger.employee == employee)
            & (ledger.leave_type == leave_type)
            & (ledger.from_date >= from_date)
            & (ledger.to_date <= end_date)
            & (ledger.transaction_type == "Leave Allocation")
            & ((ledger.is_expired == 1) & (ledger.is_carry_forward == 0))
            & (allocation.docstatus == 1)
            & (allocation.employee == employee)
            & (allocation.leave_type == leave_type)
            & (allocation.from_date <= end_date)
            & (allocation.to_date >= end_date)
        )
    ).run()
    return flt(leaves[0][0]) if leaves and leaves[0][0] else 0.0
