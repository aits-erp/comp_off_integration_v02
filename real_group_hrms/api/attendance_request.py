from datetime import datetime, timedelta

import frappe
from frappe.utils import get_time, getdate, get_timedelta

from real_group_hrms.tasks.process_employee_checkin import (
    find_closest_shift_from_punch_time,
    get_employee_allowed_shifts,
    get_shift_timings,
    get_shift_type,
)


@frappe.whitelist()
def get_leave_on_dates(employee, from_date, to_date):
    leave_on_dates = frappe.db.get_all(
        "Leave Application",
        filters={
            "employee": employee,
            "docstatus": ["!=", 2],
            "from_date": ["<=", to_date],
            "to_date": [">=", from_date],
        },
        fields=["name", "from_date", "to_date", "half_day", "half_day_date", "status"],
    )
    return leave_on_dates


@frappe.whitelist()
def closest_shift_for_time(
    time: str | None = None,
    date: str | None = None,
    employee: str | None = None,
    from_time: str | None = None,
    to_time: str | None = None,
):
    if not (date and employee):
        return None

    reference_date = getdate(date)
    reference_time = from_time or time
    if not reference_time:
        return None

    shifts = get_employee_allowed_shifts(employee, date)
    if not shifts:
        return None

    request_start = datetime.combine(reference_date, get_time(reference_time))
    if to_time:
        request_end = datetime.combine(reference_date, get_time(to_time))
        if request_end <= request_start:
            request_end += timedelta(days=1)

        shift_candidates = []
        for shift_name in shifts:
            shift_type = get_shift_type(shift_name)
            if not shift_type:
                continue

            shift_start, shift_end = get_shift_timings(
                frappe._dict(shift_type),
                request_start,
                grade=None,
                is_checkout=False,
            )
            overlap_start = max(request_start, shift_start)
            overlap_end = min(request_end, shift_end)
            overlap_seconds = max((overlap_end - overlap_start).total_seconds(), 0)
            if overlap_seconds <= 0:
                continue

            shift_candidates.append(
                {
                    "name": shift_name,
                    "contains_request": request_start >= shift_start and request_end <= shift_end,
                    "overlap_seconds": overlap_seconds,
                    "distance_from_start": abs((request_start - shift_start).total_seconds()),
                }
            )

        if shift_candidates:
            shift_candidates.sort(
                key=lambda shift: (
                    shift["contains_request"],
                    shift["overlap_seconds"],
                    -shift["distance_from_start"],
                ),
                reverse=True,
            )
            return shift_candidates[0]["name"]

    closest_shift = find_closest_shift_from_punch_time(
        shifts,
        request_start,
        date=reference_date,
        log_type="IN",
    )

    return closest_shift
