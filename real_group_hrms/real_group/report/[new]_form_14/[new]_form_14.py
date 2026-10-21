# Copyright (c) 2025, rtCamp and contributors
# For license information, please see license.txt

from datetime import date, timedelta
from importlib import import_module

import frappe
from frappe.utils import cint, format_date, get_datetime, get_timedelta, getdate

from real_group_hrms.utils import is_holiday_for_employee

dw = import_module("real_group_hrms.real_group.report.[new]_day_wise_attendance.[new]_day_wise_attendance")


def execute(filters=None):
    filters = filters or {}
    month = filters.get("month")
    year = cint(filters.get("year"))
    processed_report = bool(cint(filters.get("processed_report")))
    dates = dw.get_dates(month, year)
    start_date, end_date = dates[0], dates[-1]
    effective_end_date = min(end_date, getdate())
    columns = build_columns(dates)
    company = filters.get("company")
    branch = filters.get("branch")
    division = filters.get("division")
    department = filters.get("department")
    employee = filters.get("employee")

    employees = get_employees_for_period(company, branch, division, department, employee, start_date, end_date)
    employee_names = [emp.name for emp in employees]

    attendance_map = dw.get_attendance(employee_names, dates[0], dates[-1], month, year)
    attendance_requests_map = dw.get_attendance_requests(employee_names, dates[0], dates[-1])
    shift_map = {shift.name: shift for shift in dw.get_shifts()}

    data = []
    for idx, employee in enumerate(employees, start=1):
        emp_data = attendance_map.get(employee.name, {})

        first_half_row = get_employee_row(idx, employee)
        second_half_row = {key: "" for key in first_half_row}
        second_half_row["father_name"] = first_half_row["designation"]
        second_half_row["sr"] = ""
        counters = init_counters()

        for _date in dates:
            date_key = format_date(_date)
            if _date > effective_end_date or is_outside_service_period(employee, _date):
                first_half_row[date_key] = ""
                second_half_row[date_key] = ""
                continue
            day_snapshot = build_day_snapshot(employee, _date, emp_data, attendance_requests_map, shift_map)

            first_half_row[date_key] = day_snapshot["first_half"]
            second_half_row[date_key] = day_snapshot["second_half"]
        counted_dates = [_date for _date in dates if _date <= effective_end_date]
        counters = compute_counters_from_rows(first_half_row, second_half_row, counted_dates)

        ttl = (
            counters["ho"]
            + counters["wo"]
            + counters["p"]
            + counters["el"]
            + counters["cl"]
            + counters["co"]
            + counters["od"]
        )
        m_value = counters["p"] * 8.0
        if processed_report:
            m_value = cint(
                counters["p"] * 8.19
                + counters["el"] * 4.17
                + counters["cl"] * 4.17
                + counters["co"] * 4.17
                + counters["od"] * 8.0
            )

        apply_counters_to_row(first_half_row, counters, ttl, m_value)
        apply_counters_to_row(second_half_row, None, ttl, m_value, clear_only=True)

        data.append(first_half_row)
        data.append(second_half_row)

    return columns, data


def build_day_snapshot(employee, target_date, emp_data, attendance_requests_map, shift_map):
    """Compute raw and processed statuses and split them into half-day codes."""

    date_key = format_date(target_date)
    emp_date_data = emp_data.get(date_key, {})
    attendance_on_date = emp_date_data.get("attendance", [])
    checkins_on_date = sorted(emp_date_data.get("checkins", []), key=_get_time_from_log)

    worked_hours = sum((att.get("working_hours", 0.0) or 0.0) for att in attendance_on_date)
    day_status = "A"
    if attendance_on_date:
        primary_attendance = attendance_on_date[0]
        day_status = primary_attendance.get("custom_attendance_tag") or primary_attendance.get("status") or "A"

    shift_name = attendance_on_date[0].get("shift", "") if attendance_on_date else ""
    if not shift_name and checkins_on_date:
        shift_name = checkins_on_date[0].get("shift") or ""

    processed_value = dw.get_status(
        employee.name, target_date, emp_date_data, day_status, attendance_requests_map
    )
    status_value = dw.adjust_status_with_checkins(processed_value, checkins_on_date, shift_name, shift_map)
    if dw.has_mis_punch_request(attendance_requests_map, employee.name, target_date):
        status_value = "MIS"

    attendance_doc = attendance_on_date[0] if attendance_on_date else None
    holiday_info = is_holiday_for_employee(employee.name, target_date)
    processed_status = dw.derive_processed_status(
        status_value,
        processed_value,
        attendance_doc,
        checkins_on_date,
        worked_hours,
        holiday_info,
        employee=employee.name,
        target_date=target_date,
        attendance_requests_map=attendance_requests_map,
    )

    half_type = resolve_half_type(attendance_on_date, attendance_requests_map, employee.name, target_date)
    if not half_type and (processed_status == "HD" or status_value == "HD"):
        half_type = derive_half_day_present_half(attendance_doc, checkins_on_date, shift_name, shift_map)

    first_half, second_half = map_status_to_halves(
        processed_status, status_value, checkins_on_date, worked_hours, holiday_info, half_type, attendance_doc
    )

    return {
        "first_half": first_half,
        "second_half": second_half,
        "processed_status": processed_status,
        "status": status_value,
        "worked_hours": worked_hours,
    }


def resolve_half_type(attendance_on_date, attendance_requests_map, employee_name, target_date):
    """Pick the explicit half-day type, preferring attendance, then requests."""

    attendance_doc = attendance_on_date[0] if attendance_on_date else None
    lwp_counterpart = dw.get_lwp_half_day_counterpart_for_attendance(
        employee_name, target_date, attendance_doc, attendance_requests_map
    )
    if lwp_counterpart and lwp_counterpart.get("half_type"):
        return lwp_counterpart.get("half_type")

    half_type = _extract_half_type(attendance_doc)

    leave_application = _get_field(attendance_doc, "leave_application")
    if not half_type and leave_application:
        half_type = frappe.get_cached_value("Leave Application", leave_application, "custom_half_type")

    if half_type:
        return half_type

    requests = (
        attendance_requests_map.get(employee_name, {}).get(format_date(target_date), [])
        if attendance_requests_map
        else []
    )
    # Prefer an Official/Tour request's half over a Mis Punch request's half:
    # this half_type is used to say "which half is OD", and when both a
    # Mis Punch and a Tour/Official half-day request exist for the same date,
    # only the Official/Tour one unambiguously answers that question.
    fallback_half_type = None
    for request in requests:
        half_type = _extract_half_type(request)
        if not half_type:
            continue
        reason = (request.get("reason") or "").strip().lower()
        if reason in {"official", "tour"}:
            return half_type
        if not fallback_half_type:
            fallback_half_type = half_type

    return fallback_half_type


def _extract_half_type(source):
    return _get_field(source, "custom_half_type")


def derive_half_day_present_half(attendance_doc, checkins, shift_name, shift_map):
    in_time = _get_boundary_time(attendance_doc, checkins, "IN")
    shift_start = _get_shift_start(attendance_doc, checkins, shift_name, shift_map)
    threshold_delta = _get_half_day_split_threshold(shift_name, shift_map)

    if not in_time or not shift_start or not threshold_delta:
        return None

    half_boundary = shift_start + (threshold_delta / 2)
    if in_time > half_boundary:
        return "Second Half"
    return "First Half"


def _get_field(source, fieldname, default=None):
    if not source:
        return default
    try:
        return source.get(fieldname, default)
    except TypeError:
        return getattr(source, fieldname, default)
    except AttributeError:
        return getattr(source, fieldname, default)


def _normalize_half_type(raw_value):
    text = (raw_value or "").strip().lower()
    if not text:
        return None
    if "first" in text:
        return "FIRST"
    if "second" in text:
        return "SECOND"
    return None


def _get_time_from_log(log):
    try:
        return log.time
    except AttributeError:
        return None


def _get_boundary_time(attendance_doc, checkins, log_type):
    fieldname = "in_time" if log_type == "IN" else "out_time"
    field_value = _get_field(attendance_doc, fieldname)
    if field_value:
        return field_value

    matching_logs = [
        log for log in checkins if (_get_field(log, "log_type", "") or "").upper() == log_type
    ]
    if not matching_logs:
        return None

    matching_logs = sorted(matching_logs, key=lambda log: _get_field(log, "time"))
    target_log = matching_logs[0] if log_type == "IN" else matching_logs[-1]
    return _get_field(target_log, "time")


def _get_shift_start(attendance_doc, checkins, shift_name, shift_map):
    for log in checkins:
        shift_start = _get_field(log, "shift_start")
        if shift_start:
            return shift_start

    shift_doc = shift_map.get(shift_name) if shift_map else None
    in_time = _get_field(attendance_doc, "in_time")
    if not shift_doc or not in_time or not shift_doc.start_time:
        return None

    shift_start = in_time.replace(
        hour=shift_doc.start_time.hour,
        minute=shift_doc.start_time.minute,
        second=shift_doc.start_time.second,
        microsecond=0,
    )
    if shift_start > in_time:
        shift_start -= timedelta(days=1)
    return shift_start


def _get_half_day_split_threshold(shift_name, shift_map):
    shift_doc = shift_map.get(shift_name) if shift_map else None
    if not shift_doc:
        return None

    raw_value = _get_field(shift_doc, "custom_working_hours_threshold_for_half_day") or _get_field(
        shift_doc, "custom_half_day_threshold"
    )
    if not raw_value:
        return None

    try:
        return get_timedelta(raw_value)
    except Exception:
        return None


def build_columns(dates):
    columns = [
        {"fieldname": "sr", "fieldtype": "Data", "label": "Sr", "width": 40},
        {"fieldname": "token_no", "fieldtype": "Data", "label": "Token No.", "width": 90},
        {"fieldname": "employee_name", "fieldtype": "Data", "label": "Name of Worker", "width": 180},
        {"fieldname": "father_name", "fieldtype": "Data", "label": "Father's Name/Nature of Work", "width": 180},
    ]

    for _date in dates:
        label = f"{_date.strftime('%d')} | {_date.strftime('%a')}"
        columns.append({"fieldname": format_date(_date), "fieldtype": "Data", "label": label, "width": 100})
    columns.extend(
        [
            {"fieldname": "p", "fieldtype": "Data", "label": "P", "width": 60},
            {"fieldname": "a", "fieldtype": "Data", "label": "A", "width": 60},
            {"fieldname": "el", "fieldtype": "Data", "label": "EL", "width": 60},
            {"fieldname": "cl", "fieldtype": "Data", "label": "CL", "width": 60},
            {"fieldname": "co", "fieldtype": "Data", "label": "CO", "width": 60},
            {"fieldname": "od", "fieldtype": "Data", "label": "OD", "width": 60},
            {"fieldname": "ho", "fieldtype": "Data", "label": "HO", "width": 60},
            {"fieldname": "wo", "fieldtype": "Data", "label": "WO", "width": 60},
            {"fieldname": "ttl", "fieldtype": "Data", "label": "TTL", "width": 60},
            {"fieldname": "m", "fieldtype": "Data", "label": "M", "width": 60},
        ]
    )
    return columns


def get_employee_row(idx, employee):
    token = employee.name
    father_name = employee.custom_father_name
    designation = employee.designation
    return {
        "sr": str(idx),
        "token_no": token,
        "employee_name": employee.employee_name,
        "father_name": father_name,
        "designation": designation,
    }


def map_status_to_halves(
    processed_status, normal_status, checkins, worked_hours, holiday_info, half_type=None, attendance_doc=None
):
    half_type_code = _normalize_half_type(half_type)
    processed_code = (processed_status or "").upper()
    normal_code = (normal_status or "").upper()
    if processed_code == "LWP":
        processed_code = "LW"
    if normal_code == "LWP":
        normal_code = "LW"

    # Default to processed code, with fallbacks for specific combinations that rely on the normal status.
    code = processed_code or normal_code
    if processed_code in {"WO", "HO", "A"}:
        if processed_code == "WO":
            if normal_code == "OD":
                code = "OD"
            elif normal_code == "POW":
                code = "POW"
        elif processed_code == "HO":
            if normal_code == "OD":
                code = "OD"
            elif normal_code == "POH":
                code = "POH"
        elif processed_code == "A":
            if normal_code in {"LW", "A"}:
                code = "A"
            elif normal_code == "A1":
                code = "A1"
    leave_presence_confirmed = has_half_day_qualifying_presence(attendance_doc, worked_hours, checkins)
    presence_first_half, presence_second_half = infer_presence_halves(checkins)
    leave_presence_first_half = presence_first_half if leave_presence_confirmed else False
    leave_presence_second_half = presence_second_half if leave_presence_confirmed else False
    presence = presence_first_half or presence_second_half or (worked_hours and worked_hours > 0)
    is_day_off = bool(holiday_info.get("is_holiday")) if isinstance(holiday_info, dict) else False

    # Presence-aware handling for half-day leave combos where order depends on which half had presence.
    leave_half_map = {"HEL": "EL", "HCL": "CL", "HCO": "CO"}
    processed_leave_half_map = {"PEL": "EL", "PCL": "CL", "PCO": "CO"}
    processed_official_half_map = {"POD": "OD"}
    mis_punch_regularized = normal_code == "MIS"

    if code == "HD" and half_type_code:
        base_pair = ("P", "A") if half_type_code == "FIRST" else ("A", "P")
        return rebalance_presence_halves(base_pair, presence_first_half, force_order=True)

    if code in leave_half_map:
        leave_code = leave_half_map[code]
        return rebalance_presence_halves(
            map_half_day_leave(
                leave_code,
                leave_presence_first_half,
                leave_presence_second_half,
                default_present_first=False,
                half_type=half_type_code,
            ),
            presence_first_half,
            force_order=bool(half_type_code),
        )

    if code in processed_leave_half_map:
        leave_code = processed_leave_half_map[code]
        return rebalance_presence_halves(
            map_half_day_leave(
                leave_code,
                leave_presence_first_half,
                leave_presence_second_half,
                default_present_first=leave_presence_confirmed or mis_punch_regularized,
                half_type=half_type_code,
            ),
            presence_first_half,
            force_order=bool(half_type_code),
        )

    if code in processed_official_half_map:
        official_code = processed_official_half_map[code]
        return rebalance_presence_halves(
            map_half_day_leave(
                official_code,
                leave_presence_first_half,
                leave_presence_second_half,
                default_present_first=leave_presence_confirmed or mis_punch_regularized,
                half_type=half_type_code,
            ),
            presence_first_half,
            force_order=bool(half_type_code),
        )

    # Optional leave + holiday (HO) combos: keep HO on the half without presence.
    optional_leave_map = {"ELHO": "EL", "CLHO": "CL", "COHO": "CO"}
    if code in optional_leave_map:
        leave_code = optional_leave_map[code]
        return rebalance_presence_halves(
            map_optional_leave_half(
                leave_code,
                leave_presence_first_half,
                leave_presence_second_half,
                half_type=half_type_code,
            ),
            presence_first_half,
            force_order=bool(half_type_code),
        )

    if code in {"LWHO", "MHO", "PHO", "HHO", "ODHO"}:
        return map_optional_special(code, presence_first_half, presence_second_half)

    direct_map = {
        "P": ("P", "P"),
        "SL": ("P", "P"),
        "HD": ("P", "A"),
        "MIS": ("P", "P"),
        "A": ("A", "A"),
        "PLW": ("P", "A"),
        "CO": ("CO", "CO"),
        "HCO": ("CO", "A"),
        "EL": ("EL", "EL"),
        "HEL": ("EL", "A"),
        "CL": ("CL", "CL"),
        "HCL": ("CL", "A"),
        "OD": ("OD", "OD"),
        "WO": ("WO", "WO"),
        "POW": ("POW", "POW"),
        "HO": ("HO", "HO"),
        "POH": ("POH", "POH"),
        "POD": ("P", "OD"),
        "HOD": ("OD", "A"),
        "ELCO": ("EL", "CO"),
        "CLCO": ("CL", "CO"),
        "ODEL": ("OD", "EL"),
        "ODCL": ("OD", "CL"),
        "ODCO": ("OD", "CO"),
    }

    # Explicit half-day ordering when OD is only for one half (attendance request) and leave is for the other.
    if half_type_code and code in {"ODEL", "ODCL", "ODCO", "HOD"}:
        leave_half = {
            "ODEL": "EL",
            "ODCL": "CL",
            "ODCO": "CO",
            "HOD": "OD",
        }.get(code, "A")
        if code == "HOD":
            base_pair = ("OD", "A") if half_type_code == "FIRST" else ("A", "OD")
        else:
            base_pair = (leave_half, "OD") if half_type_code == "FIRST" else ("OD", leave_half)
        return rebalance_presence_halves(base_pair, presence_first_half, force_order=True)

    if code in direct_map:
        return rebalance_presence_halves(direct_map[code], presence_first_half, force_order=bool(half_type_code))

    if code.startswith("H") and len(code) > 1:
        tail = code[1:]
        if presence:
            base_pair = ("P", tail)
            return rebalance_presence_halves(base_pair, presence_first_half, force_order=bool(half_type_code))
        return (tail, "A")

    if is_day_off and code == "OD":
        return rebalance_presence_halves(("OD", "OD"), presence_first_half, force_order=bool(half_type_code))

    if code:
        return rebalance_presence_halves((code, code), presence_first_half, force_order=bool(half_type_code))

    return "", ""


def infer_presence_halves(checkins):
    valid_pairs = get_valid_in_out_pairs(checkins)
    if not valid_pairs:
        return False, False
    has_first = False
    has_second = False
    logs_for_presence = [pair[0] for pair in valid_pairs]
    try:
        for log in sorted(logs_for_presence, key=_get_time_from_log):
            ts = _get_time_from_log(log)
            if not ts:
                continue
            try:
                hour_val = ts.time().hour
            except AttributeError:
                try:
                    hour_val = ts.hour
                except AttributeError:
                    hour_val = None
            if hour_val is None:
                continue
            if hour_val < 13:
                has_first = True
            else:
                has_second = True
    except Exception:
        return True, False

    return has_first, has_second


def has_confirmed_presence(worked_hours, checkins):
    if worked_hours and worked_hours > 0:
        return True
    return has_valid_in_out_pair(checkins)


def has_half_day_qualifying_presence(attendance_doc, worked_hours, checkins):
    checker = getattr(dw, "_has_half_day_qualifying_presence", None)
    if callable(checker):
        return checker(attendance_doc, checkins, worked_hours)
    return has_confirmed_presence(worked_hours, checkins)


def has_valid_in_out_pair(checkins):
    return bool(get_valid_in_out_pairs(checkins))


def get_valid_in_out_pairs(checkins):
    if not checkins:
        return []

    in_logs = sorted(
        [log for log in checkins if (_get_field(log, "log_type", "") or "").upper() == "IN"],
        key=_get_time_from_log,
    )
    out_logs = sorted(
        [log for log in checkins if (_get_field(log, "log_type", "") or "").upper() == "OUT"],
        key=_get_time_from_log,
    )

    valid_pairs = []
    for idx in range(min(len(in_logs), len(out_logs))):
        in_time = _get_time_from_log(in_logs[idx])
        out_time = _get_time_from_log(out_logs[idx])
        if not in_time or not out_time:
            continue

        if get_datetime(out_time) > get_datetime(in_time):
            valid_pairs.append((in_logs[idx], out_logs[idx]))

    return valid_pairs


def rebalance_presence_halves(pair, presence_first_half, force_order=False):
    if not pair:
        return "", ""
    if force_order:
        return pair
    presence_codes = {"P", "POH", "POW", "POD", "PHO", "PEL", "PCL", "PCO", "OD"}
    first, second = pair
    if presence_first_half:
        if second in presence_codes and first not in presence_codes:
            return second, first
        return pair

    if first in presence_codes and second not in presence_codes:
        return second, first
    return pair


def map_half_day_leave(leave_code, presence_first_half, presence_second_half, default_present_first, half_type=None):
    half_type_code = _normalize_half_type(half_type)
    default_other_half = "P" if default_present_first else "A"

    if half_type_code == "FIRST":
        return leave_code, ("P" if presence_second_half else default_other_half)
    if half_type_code == "SECOND":
        return ("P" if presence_first_half else default_other_half), leave_code

    fallback_other_half = "P" if (presence_first_half or presence_second_half or default_present_first) else "A"
    if presence_first_half and not presence_second_half:
        return fallback_other_half, leave_code
    if presence_second_half and not presence_first_half:
        return leave_code, fallback_other_half
    if default_present_first:
        return fallback_other_half, leave_code
    return leave_code, fallback_other_half


def map_optional_leave_half(leave_code, presence_first_half, presence_second_half, half_type=None):
    half_type_code = _normalize_half_type(half_type)
    if half_type_code == "FIRST":
        return leave_code, ("P" if presence_second_half else "HO")
    if half_type_code == "SECOND":
        return ("P" if presence_first_half else "HO"), leave_code

    if presence_first_half and not presence_second_half:
        return "P", leave_code
    if presence_second_half and not presence_first_half:
        return leave_code, "P"
    return leave_code, ("P" if (presence_first_half or presence_second_half) else "HO")


def map_optional_special(code, presence_first_half, presence_second_half):
    base_map = {
        "LWHO": ("A", "HO"),
        "MHO": ("P", "HO"),
        "PHO": ("P", "HO"),
        "HHO": ("A", "HO"),
        "ODHO": ("OD", "HO"),
    }
    base = base_map.get(code, ("", ""))

    if presence_first_half and not presence_second_half:
        return "P", base[1] or "HO"
    if presence_second_half and not presence_first_half:
        return base[1] or "HO", "P"
    if presence_first_half and presence_second_half:
        return "P", base[1] or "HO"
    return base


def init_counters():
    return {"p": 0.0, "a": 0.0, "el": 0.0, "cl": 0.0, "co": 0.0, "od": 0.0, "ho": 0.0, "wo": 0.0}


def add_half_day_to_counters(counters, code):
    if not code:
        return
    key = code.upper()
    target = None
    if key in {"P", "MIS", "SL"}:
        target = "p"
    elif key in {"A", "A1", "LW"}:
        target = "a"
    elif key == "EL":
        target = "el"
    elif key == "CL":
        target = "cl"
    elif key == "CO":
        target = "co"
    elif key == "OD":
        target = "od"
    elif key == "HO" or key == "POH" or key == "PHO" or key == "HHO":
        target = "ho"
    elif key == "WO" or key == "POW":
        target = "wo"

    if target:
        counters[target] += 0.5


def compute_counters_from_rows(first_row, second_row, dates):
    counters = init_counters()
    for _date in dates:
        date_key = format_date(_date)
        add_half_day_to_counters(counters, first_row.get(date_key))
        add_half_day_to_counters(counters, second_row.get(date_key))
    return counters


def apply_counters_to_row(row, counters, ttl, m_value, clear_only=False):
    fields = ["p", "a", "el", "cl", "co", "od", "ho", "wo", "ttl", "m"]
    if clear_only:
        for field in fields:
            row[field] = ""
        return

    row.update(
        {
            "p": counters.get("p", 0.0),
            "a": counters.get("a", 0.0),
            "el": counters.get("el", 0.0),
            "cl": counters.get("cl", 0.0),
            "co": counters.get("co", 0.0),
            "od": counters.get("od", 0.0),
            "ho": counters.get("ho", 0.0),
            "wo": counters.get("wo", 0.0),
            "ttl": ttl,
            "m": m_value,
        }
    )


def get_employees_for_period(company, branch, division, department, employee, start_date: date, end_date: date):
    filters = {"company": company, "branch": branch, "status": ["in", ["Active", "Left"]]}
    if division:
        filters["custom_division"] = division
    if department:
        filters["department"] = department
    if employee:
        filters["name"] = employee

    employees = frappe.get_all(
        "Employee",
        filters=filters,
        fields=["*"],
    )

    in_period = []
    for emp in employees:
        doj = getdate(emp.get("date_of_joining")) if emp.get("date_of_joining") else None
        dor = getdate(emp.get("relieving_date")) if emp.get("relieving_date") else None
        if doj and doj > end_date:
            continue
        if dor and dor < start_date:
            continue
        in_period.append(emp)
    return sorted(in_period, key=dw.get_employee_sort_key)


def is_outside_service_period(employee, current_date: date) -> bool:
    doj = getdate(employee.get("date_of_joining")) if employee.get("date_of_joining") else None
    dor = getdate(employee.get("relieving_date")) if employee.get("relieving_date") else None
    if doj and current_date < doj:
        return True
    if dor and current_date > dor:
        return True
    return False
