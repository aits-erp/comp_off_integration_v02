from datetime import date, time, timedelta

import frappe
from frappe.utils import add_days, date_diff, get_datetime, get_first_day, get_last_day, get_time, getdate
from frappe.utils.caching import redis_cache
from hrms.hr.utils import get_leave_allocations
from pypika.functions import Count


def convert_time_to_seconds(time_str: str | time | timedelta) -> float:
    if not time_str:
        return 0.0
    if isinstance(time_str, str):
        time_str = get_time(time_str)
    if isinstance(time_str, timedelta):
        return time_str.total_seconds()
    return timedelta(hours=time_str.hour, minutes=time_str.minute, seconds=time_str.second).total_seconds()


def convert_time_to_minutes(time_str: str | time) -> float:
    if not time_str:
        return 0.0
    seconds = convert_time_to_seconds(time_str)
    return seconds / 60


def convert_time_to_hours(time_str: str | time) -> float:
    if not time_str:
        return 0.0
    seconds = convert_time_to_seconds(time_str)
    return seconds / 3600


@frappe.whitelist()
def is_holiday_for_employee(employee: str, date, weekly_holiday_name=None):
    from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee

    data = {}
    holiday_list = get_holiday_list_for_employee(employee)

    is_holiday = frappe.db.get_value(
        "Holiday",
        {
            "parent": holiday_list,
            "holiday_date": getdate(date),
            "parenttype": "Holiday List",
            "parentfield": "holidays",
        },
        ["name", "custom_unplanned", "custom_half_day", "custom_half_type"],
    )
    if is_holiday:
        data = {
            "is_holiday": True,
            "holiday_name": is_holiday[0],
            "is_weekly_off": False,
            "is_unplanned_holiday": is_holiday[1],
            "is_half_day": is_holiday[2],
            "half_type": is_holiday[3],
        }
        return data
    else:
        if not weekly_holiday_name:
            weekly_holiday_name = get_weekly_off_based_on_date(employee, date)
        is_holiday = frappe.db.get_value(
            "Weekly Off Holiday",
            {
                "parent": weekly_holiday_name,
                "holiday_date": getdate(date),
                "parenttype": "Weekly Off List",
                "parentfield": "holidays",
            },
            "name",
        )
        if is_holiday:
            data = {
                "is_holiday": True,
                "holiday_name": is_holiday,
                "is_weekly_off": True,
                "is_unplanned_holiday": False,
                "is_half_day": False,
                "half_type": None,
            }
            return data

    return False


def normalize_half_type(half_type: str | None) -> str | None:
    if not half_type:
        return None

    normalized = half_type.strip().lower().replace("_", " ")
    if normalized in {"first", "first half"}:
        return "first half"
    if normalized in {"second", "second half"}:
        return "second half"
    return normalized or None


def half_types_match(first_half_type: str | None, second_half_type: str | None) -> bool:
    first = normalize_half_type(first_half_type)
    second = normalize_half_type(second_half_type)
    return bool(first and second and first == second)


def half_types_differ(first_half_type: str | None, second_half_type: str | None) -> bool:
    first = normalize_half_type(first_half_type)
    second = normalize_half_type(second_half_type)
    return bool(first and second and first != second)


def holiday_matches_requested_half(holiday: dict | None, requested_half_type: str | None) -> bool:
    if not holiday or not holiday.get("is_holiday") or not holiday.get("is_half_day"):
        return False
    return half_types_match(holiday.get("half_type"), requested_half_type)


def holiday_complements_requested_half(holiday: dict | None, requested_half_type: str | None) -> bool:
    if not holiday or not holiday.get("is_holiday") or not holiday.get("is_half_day"):
        return False
    return half_types_differ(holiday.get("half_type"), requested_half_type)


def has_absent_attendance(employee: str, attendance_date) -> bool:
    """Return True if there is a non-cancelled Attendance marked Absent for the given date."""

    return bool(
        frappe.db.exists(
            "Attendance",
            {
                "employee": employee,
                "attendance_date": getdate(attendance_date),
                "status": "Absent",
                "docstatus": ["!=", 2],
            },
        )
    )


@frappe.whitelist()
def find_half_day(employee: str, from_date, to_date):
    from_date = getdate(from_date)
    to_date = getdate(to_date)
    while from_date <= to_date:
        half_day = is_holiday_for_employee(employee, from_date)
        if half_day:
            return from_date
        from_date = add_days(from_date, 1)
    return False


def get_holiday_dates_for_employee(employee: str, from_date, to_date, weekly_holiday_name=None):
    from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee

    from_date = getdate(from_date)
    to_date = getdate(to_date)

    # Get employee's base holiday list
    holiday_list = get_holiday_list_for_employee(employee)

    # Fetch static holidays from holiday list
    holidays = frappe.get_all(
        "Holiday",
        filters={"parent": holiday_list, "holiday_date": ("between", [from_date, to_date])},
        pluck="holiday_date",
        order_by="holiday_date",
    )

    # Now dynamically check weekly offs
    weekly_holidays = []
    total_days = date_diff(to_date, from_date) + 1

    for i in range(total_days):
        current_date = add_days(from_date, i)
        weekly_off_name = get_weekly_off_based_on_date(employee, current_date)

        if not weekly_off_name:
            continue  # No weekly off defined for this date range or employee

        # Fetch weekly off for that specific date
        weekly_off = frappe.db.exists(
            "Weekly Off Holiday",
            {"parent": weekly_off_name, "holiday_date": current_date},
        )
        if weekly_off:
            weekly_holidays.append(current_date)

    return list(set(holidays + weekly_holidays))


def fetch_leaves_for_working_days(employee: str, from_date, to_date, on_working_days: int):
    Leave_Type = frappe.qb.DocType("Leave Type")
    Attendance = frappe.qb.DocType("Attendance")
    query = (
        frappe.qb.from_(Attendance)
        .left_join(Leave_Type)
        .on(Attendance.leave_type == Leave_Type.name)
        .select(Count(Attendance.name))
        .where(
            (Attendance.employee == employee)
            & (Attendance.attendance_date.between(from_date, to_date))
            & (Attendance.status.notin(["Absent"]))
            & (Attendance.docstatus.notin([2]))
            & ((Leave_Type.is_lwp == 0) | (Leave_Type.is_lwp.isnull()))
        )
    )
    working_days = query.run()[0][0] or 0
    new_leaves = working_days // on_working_days

    return new_leaves


def get_remaining_days_for_pro_rated(employee: str, from_date, to_date, on_working_days: int):
    Leave_Type = frappe.qb.DocType("Leave Type")
    Attendance = frappe.qb.DocType("Attendance")
    query = (
        frappe.qb.from_(Attendance)
        .left_join(Leave_Type)
        .on(Attendance.leave_type == Leave_Type.name)
        .select(Count(Attendance.name))
        .where(
            (Attendance.employee == employee)
            & (Attendance.attendance_date.between(from_date, to_date))
            & (Attendance.status.notin(["Absent"]))
            & (Attendance.docstatus.notin([2]))
            & ((Leave_Type.is_lwp == 0) | (Leave_Type.is_lwp.isnull()))
        )
    )
    working_days = query.run()[0][0] or 0
    return working_days % on_working_days


def allocate_leaves_for_worked_days():
    from frappe.utils import cint

    leave_types = get_wo_leaves()
    today = frappe.flags.current_date or getdate()

    for leave_type in leave_types:
        leave_allocations = get_leave_allocations(today, leave_type.name)

        for allocation in leave_allocations:
            if not allocation.leave_policy_assignment and not allocation.leave_policy:
                continue

            leave_policy = (
                allocation.leave_policy
                if allocation.leave_policy
                else frappe.db.get_value("Leave Policy Assignment", allocation.leave_policy_assignment, "leave_policy")
            )

            annual_allocation = cint(
                frappe.db.get_value(
                    "Leave Policy Detail",
                    filters={"parent": leave_policy, "leave_type": leave_type.name},
                    fieldname=["annual_allocation"],
                )
                or 0
            )

            on_working_days = cint(leave_type.custom_number_of_working_days or 20)
            new_leaves = fetch_leaves_for_working_days(
                allocation.employee,
                allocation.from_date,
                allocation.to_date,
                on_working_days,
            )

            allocation_doc = frappe.get_doc("Leave Allocation", allocation.name)

            already_allocated = cint(allocation_doc.total_leaves_allocated or 0)

            incremental_leaves = new_leaves - already_allocated

            if incremental_leaves > 0:
                new_total = min(new_leaves, annual_allocation)
                added_leaves = new_total - already_allocated

                if added_leaves > 0:
                    allocation_doc.new_leaves_allocated = added_leaves
                    allocation_doc.save(ignore_permissions=True)
                    frappe.logger().info(
                        f"[Earned Leave] {allocation.employee} got +{added_leaves} "
                        f"leaves (Total: {new_total}) for {leave_type.name}"
                    )


def get_wo_leaves():
    return frappe.get_all(
        "Leave Type",
        fields=["*"],
        filters={"custom_calculate_based_on_working_days": 1, "custom_avail_leave_in_next_calendar_year": 0},
    )


def get_actual_leave_balance_cf(employee: str, leave_type: str) -> float:
    leaves = frappe.get_all(
        "Leave Ledger Entry",
        filters={
            "is_lwp": False,
            "docstatus": ["!=", 2],
            "is_carry_forward": False,
            "is_expired": False,
            "leave_type": leave_type,
            "employee": employee,
        },
        pluck="leaves",
    )

    return sum(leaves)


def get_weekly_off_based_on_date(employee: str, date: date | str):
    if isinstance(date, str):
        date = getdate(date)
    weekly_list = get_weekly_off(employee)
    # Sort by valid_from in descending order to find the most recent applicable one first
    sorted_weekly_list = sorted(weekly_list, key=lambda w: w.valid_from, reverse=True)
    for w in sorted_weekly_list:
        if date >= w.valid_from:
            return w.weekly_off
    return frappe.db.get_value("Employee", employee, "custom_weekly_holiday_list", cache=True)


@redis_cache()
def get_weekly_off(employee: str):
    offs = frappe.get_all("Weekly Holiday Update Request", filters={"employee": employee, "docstatus": 1}, fields=["*"])
    return offs


def validate_employee_and_user(username: str):
    if frappe.db.exists("Employee", username):
        return True
    return False


@frappe.whitelist()
def set_geolocation_from_coordinates(doc):
    if doc.get("employee"):
        posting_location = frappe.db.get_value("Employee", doc.employee, "custom_is_remote_office")
        if not posting_location:
            return

    if not (doc.custom_latitude and doc.custom_longitude):
        return

    doc.custom_location = frappe.json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {},
                    # geojson needs coordinates in reverse order: long, lat instead of lat, long
                    "geometry": {"type": "Point", "coordinates": [doc.custom_longitude, doc.custom_latitude]},
                }
            ],
        }
    )


def get_distance_between_coordinates(lat1, long1, lat2, long2):
    from math import asin, cos, pi, sqrt

    r = 6371
    p = pi / 180

    a = 0.5 - cos((lat2 - lat1) * p) / 2 + cos(lat1 * p) * cos(lat2 * p) * (1 - cos((long2 - long1) * p)) / 2
    return 2 * r * asin(sqrt(a)) * 1000


def check_effective_date(from_date, today, frequency, allocate_on_day):
    from dateutil import relativedelta

    from_date = get_datetime(from_date)
    today = frappe.flags.current_date or get_datetime(today)
    rd = relativedelta.relativedelta(today, from_date)

    expected_date = {
        "First Day": get_first_day(today),
        "Last Day": get_last_day(today),
        "Date of Joining": from_date,
    }[allocate_on_day]

    if expected_date.day == today.day:
        if frequency == "Monthly":
            return True
        elif frequency == "Quarterly" and rd.months % 3 == 0:
            return True
        elif frequency == "Half-Yearly" and rd.months % 6 == 0:
            return True
        elif frequency == "Yearly" and rd.months % 12 == 0:
            return True

    return False


class SandwichPolicyError(frappe.ValidationError):
    pass
