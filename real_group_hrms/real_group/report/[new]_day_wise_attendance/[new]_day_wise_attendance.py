# Copyright (c) 2025, rtCamp and contributors
# For license information, please see license.txt

import calendar
from datetime import date, datetime, timedelta
from datetime import time as dt_time

import frappe
from frappe.utils import add_days, cint, cstr, format_date, get_datetime, get_time, getdate
from frappe.utils.caching import redis_cache

from real_group_hrms.utils import convert_time_to_hours, is_holiday_for_employee

month_order = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

top_row_status_split = {
    "HO": {"holiday": 1},
    "POH": {"holiday": 1},
    "PHO": {"holiday": 0.5},
    "HHO": {"holiday": 0.5},
    "MHO": {"holiday": 0.5},
    "WO": {"weekly_off": 1},
    "POW": {"weekly_off": 1},
    "EL": {"leaves": 1},
    "HEL": {"leaves": 0.5},
    "PEL": {"leaves": 0.5},
    "CL": {"leaves": 1},
    "HCL": {"leaves": 0.5},
    "PCL": {"leaves": 0.5},
    "CO": {"leaves": 1},
    "HCO": {"leaves": 0.5},
    "PCO": {"leaves": 0.5},
    "LW": {"leaves": 1},
    "LWP": {"leaves": 1},
    "HLW": {"leaves": 0.5},
    "PLW": {"leaves": 0.5},
    "ELHO": {"holiday": 0.5, "leaves": 0.5},
    "CLHO": {"holiday": 0.5, "leaves": 0.5},
    "COHO": {"holiday": 0.5, "leaves": 0.5},
    "LWHO": {"holiday": 0.5, "leaves": 0.5},
    "ELCO": {"leaves": 1},
    "CLCO": {"leaves": 1},
    "OD": {"od": 1},
    "HOD": {"od": 0.5},
    "POD": {"od": 0.5},
    "ODHO": {"holiday": 0.5, "od": 0.5},
    "ODEL": {"leaves": 0.5, "od": 0.5},
    "ODCL": {"leaves": 0.5, "od": 0.5},
    "ODCO": {"leaves": 0.5, "od": 0.5},
}

summary_status_split = {
    "P": {"present": 1},
    "EW": {"present": 1},
    "SL": {"present": 1},
    "POH": {"present": 1},
    "POW": {"present": 1},
    "A": {"absent": 1},
    "A1": {"absent": 1},
    "HD": {"present": 0.5, "absent": 0.5},
    "PLW": {"present": 0.5, "absent": 0.5},
    "PEL": {"present": 0.5},
    "PCL": {"present": 0.5},
    "PCO": {"present": 0.5},
    "POD": {"present": 0.5},
    "PHO": {"present": 0.5},
    "HHO": {"absent": 0.5},
    "LWHO": {"absent": 0.5},
}


def execute(filters=None):
    month = filters.get("month")
    year = cint(filters.get("year"))
    include_processed_status = bool(cint(filters.get("processed_attendance")))
    columns, data = get_columns(month, year), []
    company = filters.get("company")
    branch = filters.get("branch")
    division = filters.get("division")
    department = filters.get("department")
    employee = filters.get("employee")
    dates = get_dates(month, year)
    employees = get_employees(company, branch, division, department, employee, dates[0], dates[-1])
    employee_names = [emp.name for emp in employees]
    attendance_map = get_attendance(employee_names, dates[0], dates[-1], month, year)
    attendance_requests_map = get_attendance_requests(employee_names, dates[0], dates[-1])
    shifts = get_shifts()
    shift_map = {shift.name: shift for shift in shifts}
    for employee in employees:
        info = {"sr": "PAYCODE, CARD NO. & NAME"}

        emp_data = attendance_map.get(employee.name, {})
        max_checkins = emp_data.get("max_checkins", 0)

        max_pairs = 0
        pairs = ((max_checkins) + 1) // 2
        max_pairs = max(max_pairs, pairs)

        (row_keys, hours_worked, extra_worked, processed_status, status, shift) = get_rows(max_pairs, dates)
        summary_presence_totals = init_summary_presence_totals()
        total_hours = 0.0
        extra_status_totals = init_top_row_status_totals()

        for _date in dates:
            date_str = format_date(_date)
            if is_outside_service_period(employee, _date):
                if include_processed_status:
                    processed_status[date_str] = None
                status[date_str] = None
                shift[date_str] = None
                continue

            emp_date_data = emp_data.get(date_str, {})
            checkins_on_date = emp_date_data.get("checkins", [])
            emp_checkins = sorted(checkins_on_date, key=lambda x: x.time)
            in_out_logs = get_logs(emp_checkins)
            attendance_on_date = emp_date_data.get("attendance", [])

            for i in range(0, len(row_keys), 2):
                pair_index = i // 2
                in_row = row_keys[i]

                if in_out_logs and pair_index < len(in_out_logs.get("IN", [])):
                    in_row[date_str] = format_time_hhmm(in_out_logs["IN"][pair_index]["time"])

                if i + 1 < len(row_keys):
                    out_row = row_keys[i + 1]
                    if in_out_logs and pair_index < len(in_out_logs.get("OUT", [])):
                        out_row[date_str] = format_time_hhmm(in_out_logs["OUT"][pair_index]["time"])
            worked_hours = 0.0
            day_status = "A"
            if attendance_on_date:
                for attendance in attendance_on_date:
                    worked_hours += attendance.get("working_hours", 0.0)
                    day_status = attendance.get("custom_attendance_tag", None) or attendance.get("status")
            total_hours += worked_hours
            worked_hours_value = worked_hours
            hours_worked[date_str] = (
                format_time_hhmm(timedelta(seconds=round(worked_hours_value * 3600 / 60) * 60))
                if worked_hours_value
                else ""
            )
            day_shift_name = attendance_on_date[0].get("shift", "") if attendance_on_date else ""
            if not day_shift_name and emp_checkins:
                day_shift_name = emp_checkins[0].get("shift") or ""

            holiday_info = is_holiday_for_employee(employee.name, _date)
            shift[date_str] = day_shift_name
            if day_shift_name:
                shift_type = shift_map.get(day_shift_name)
                if shift_type and shift_type.custom_shift_time and (worked_hours_value or 0) > 0:
                    shift_time = get_time(shift_type.custom_shift_time)
                    worked_time = get_time(timedelta(hours=worked_hours_value))
                    if holiday_info and holiday_info.get("is_holiday"):
                        extra_worked[date_str] = format_time_hhmm(timedelta(hours=worked_hours_value))
                    else:
                        dt1 = datetime.combine(date.today(), shift_time)
                        dt2 = datetime.combine(date.today(), worked_time)
                        delta = dt2 - dt1
                        if delta.total_seconds() > 0:
                            extra_worked[date_str] = format_time_hhmm(delta)
                if shift_type and shift_type.custom_shift_time and not worked_hours_value:
                    if holiday_info and holiday_info.get("is_holiday"):
                        holiday_extra_work = get_holiday_extra_work(emp_checkins)
                        if holiday_extra_work:
                            extra_worked[date_str] = holiday_extra_work
            processed_value = get_status(
                employee.name, _date, emp_date_data, day_status, attendance_requests_map
            )
            status_value = adjust_status_with_checkins(processed_value, emp_checkins, day_shift_name, shift_map)
            if has_mis_punch_request(
                attendance_requests_map, employee.name, _date
            ):  # if theres mispunch status should be mispunch
                status_value = "MIS"
            status[date_str] = status_value
            attendance_doc = attendance_on_date[0] if attendance_on_date else None
            processed_status_value = derive_processed_status(
                status_value,
                processed_value,
                attendance_doc,
                emp_checkins,
                worked_hours_value,
                holiday_info,
                employee=employee.name,
                target_date=_date,
                attendance_requests_map=attendance_requests_map,
            )
            summary_status_value = processed_status_value if include_processed_status else status_value
            add_top_row_status_totals(extra_status_totals, summary_status_value)
            add_summary_presence_totals(summary_presence_totals, summary_status_value)
            if include_processed_status:
                processed_status[date_str] = processed_status_value
        summary_dates = []
        temp_date = dates[0]
        for _ in range(11):
            summary_dates.append(format_date(temp_date))
            temp_date = add_days(temp_date, days=1)
        if len(summary_dates) >= 11:
            total_time = timedelta(seconds=round(total_hours * 3600 / 60) * 60)
            info[summary_dates[0]] = employee["name"]
            info[summary_dates[1]] = employee["employee_name"]
            info[summary_dates[2]] = employee.get("designation", "")
            info[summary_dates[3]] = employee.get("department", "")
            info[summary_dates[4]] = (
                f"Present: {format_top_row_status_value(summary_presence_totals['present'])}"
            )
            info[summary_dates[5]] = (
                f"Absent: {format_top_row_status_value(summary_presence_totals['absent'])}"
            )
            info[summary_dates[6]] = f"Hours: {format_time_hhmm(total_time)}"
            info[summary_dates[7]] = f"Holiday: {format_top_row_status_value(extra_status_totals['holiday'])}"
            info[summary_dates[8]] = f"Weekly Off: {format_top_row_status_value(extra_status_totals['weekly_off'])}"
            info[summary_dates[9]] = f"Leaves: {format_top_row_status_value(extra_status_totals['leaves'])}"
            info[summary_dates[10]] = f"OD: {format_top_row_status_value(extra_status_totals['od'])}"

        extra_worked_sub = {"sr": "E Work"}  ## client wants extra work to be empty
        data.append(info)
        data.extend(row_keys)
        data.append(hours_worked)
        data.append(extra_worked_sub)
        data.append(status)
        if include_processed_status:
            data.append(processed_status)
        data.append(shift)

    return columns, data


def get_columns(month: str, year: int):
    columns = [{"fieldname": "sr", "fieldtype": "Data", "label": "", "width": "250"}]
    dates = get_dates(month, year)
    for _date in dates:
        columns.append(
            {
                "fieldname": format_date(_date),
                "fieldtype": "Data",
                "label": format_date(_date),
                "width": "70px",
            }
        )
    return columns


@redis_cache
def get_dates(month: str, year: int):
    if not month or not year:
        today = getdate()
        month = month_order[today.month - 1]
        year = today.year
    month_index = month_order.index(month) + 1
    start_date = date(year, month_index, 1)
    last_day = calendar.monthrange(year, month_index)[1]
    end_date = date(year, month_index, last_day)

    dates = []
    while start_date <= end_date:
        dates.append(start_date)
        start_date = add_days(start_date, 1)
    return dates


def get_employees(company, branch, division=None, department=None, employee=None, start_date=None, end_date=None):
    filters = {"company": company, "branch": branch, "status": ["in", ["Active", "Left"]]}
    if division:
        filters["custom_division"] = division
    if department:
        filters["department"] = department
    if employee:
        filters["name"] = employee

    employees = frappe.get_all("Employee", filters=filters, fields=["*"])
    employees = filter_employees_for_period(employees, start_date, end_date)
    return sorted(employees, key=get_employee_sort_key)


def get_employee_sort_key(employee):
    employee_id = cstr(employee.get("name") or "").strip()
    if employee_id.isdigit():
        return (0, int(employee_id))
    return (1, employee_id.lower())


def init_top_row_status_totals():
    return {"holiday": 0.0, "weekly_off": 0.0, "leaves": 0.0, "od": 0.0}


def init_summary_presence_totals():
    return {"present": 0.0, "absent": 0.0}


def add_top_row_status_totals(totals, status_code):
    if not totals or not status_code:
        return

    contributions = top_row_status_split.get((status_code or "").strip().upper(), {})
    for key, value in contributions.items():
        totals[key] = totals.get(key, 0.0) + value


def add_summary_presence_totals(totals, status_code):
    if not totals or not status_code:
        return

    contributions = summary_status_split.get((status_code or "").strip().upper(), {})
    for key, value in contributions.items():
        totals[key] = totals.get(key, 0.0) + value


def format_top_row_status_value(value):
    numeric_value = round(float(value or 0), 2)
    if numeric_value.is_integer():
        return int(numeric_value)
    return numeric_value


def filter_employees_for_period(employees, start_date=None, end_date=None):
    if not start_date or not end_date:
        return employees

    in_period = []
    for employee in employees:
        doj = getdate(employee.get("date_of_joining")) if employee.get("date_of_joining") else None
        dor = getdate(employee.get("relieving_date")) if employee.get("relieving_date") else None
        if doj and doj > end_date:
            continue
        if dor and dor < start_date:
            continue
        in_period.append(employee)

    return in_period


def is_outside_service_period(employee, current_date: date) -> bool:
    doj = getdate(employee.get("date_of_joining")) if employee.get("date_of_joining") else None
    dor = getdate(employee.get("relieving_date")) if employee.get("relieving_date") else None
    if doj and current_date < doj:
        return True
    if dor and current_date > dor:
        return True
    return False


def get_attendance(employees: list, start_date: date, end_date: date, month: str, year: int):
    dates = get_dates(month, year)
    if not employees:
        return {}
    data = frappe.get_all(
        "Attendance",
        filters={
            "employee": ["in", employees],
            "attendance_date": ["between", (start_date, end_date)],
            "docstatus": ["!=", 2],
        },
        fields=["*"],
    )
    attendance_names = [d.name for d in data]
    datetime_range = (
        datetime.combine(start_date, datetime.min.time()),
        datetime.combine(end_date, datetime.max.time().replace(microsecond=0)),
    )
    checkin_or_filters = [
        ["shift_start", "between", datetime_range],
        ["time", "between", datetime_range],
    ]
    if attendance_names:
        checkin_or_filters.append(["attendance", "in", attendance_names])

    checkin_filters = {"employee": ["in", employees]}
    employee_checkins = frappe.get_all(
        "Employee Checkin",
        filters=checkin_filters,
        or_filters=checkin_or_filters,
        fields=["*"],
    )
    attendance_map = {}
    for employee in employees:
        attendance = [d for d in data if d.employee == employee]
        checkins = [d for d in employee_checkins if d.employee == employee]
        attendance_map[employee] = {"max_checkins": 0}
        for _date in dates:
            attendance_map[employee][format_date(_date)] = {}
            date = getdate(_date)
            attendance_on_date = [d for d in attendance if getdate(d.attendance_date) == date]
            checkins_on_date = []
            for d in checkins:
                reference_datetime = d.get("shift_start") or d.get("time")
                if reference_datetime and getdate(reference_datetime) == date:
                    checkins_on_date.append(d)
            length = len(checkins_on_date)
            if length > attendance_map[employee]["max_checkins"]:
                attendance_map[employee]["max_checkins"] = length
            attendance_map[employee][format_date(date)]["attendance"] = attendance_on_date
            attendance_map[employee][format_date(date)]["checkins"] = checkins_on_date

    return attendance_map


def get_attendance_requests(employees: list, start_date: date, end_date: date):
    if not employees:
        return {}

    requests = frappe.get_all(
        "Attendance Request",
        filters={
            "employee": ["in", employees],
            "docstatus": ["!=", 2],
            "from_date": ["<=", end_date],
            "to_date": [">=", start_date],
        },
        fields=[
            "name",
            "employee",
            "reason",
            "from_date",
            "to_date",
            "half_day",
            "half_day_date",
            "custom_half_type",
            "docstatus",
        ],
    )

    request_map = {emp: {} for emp in employees}

    for request in requests:
        employee = request.employee
        if employee not in request_map:
            request_map[employee] = {}

        if request.get("half_day") and request.get("half_day_date"):
            target_date = getdate(request.half_day_date)
            if start_date <= target_date <= end_date:
                date_key = format_date(target_date)
                request_map[employee].setdefault(date_key, []).append(request)
            continue

        current = max(getdate(request.from_date), start_date)
        to_date = min(getdate(request.to_date), end_date)
        while current <= to_date:
            date_key = format_date(current)
            request_map[employee].setdefault(date_key, []).append(request)
            current = add_days(current, 1)

    return request_map


def has_mis_punch_request(request_map: dict, employee: str, target_date: date):
    employee_requests = request_map.get(employee)
    if not employee_requests:
        return False

    requests_on_date = employee_requests.get(format_date(target_date), [])
    for request in requests_on_date:
        reason = (request.get("reason") or "").strip().lower()
        if reason == "mis punch":
            return True

    return False


def has_full_day_official_request(request_map: dict, employee: str, target_date: date) -> bool:
    employee_requests = request_map.get(employee)
    if not employee_requests:
        return False

    requests_on_date = employee_requests.get(format_date(target_date), [])
    if not requests_on_date:
        return False

    matching_half_day_requests = []
    half_types = set()

    for request in requests_on_date:
        reason = (request.get("reason") or "").strip().lower()
        if reason not in {"official", "tour"}:
            continue

        if not request.get("half_day"):
            return True

        half_day_date = request.get("half_day_date")
        if half_day_date and getdate(half_day_date) == target_date:
            matching_half_day_requests.append(request)
            half_type = (request.get("custom_half_type") or "").strip().lower()
            if half_type:
                half_types.add(half_type)

    if len(half_types) >= 2:
        return True

    return len(matching_half_day_requests) >= 2 and not half_types


def get_rows(pairs, dates):
    paired_rows = []

    for i in range(pairs):
        in_row = {"sr": f"IN{i + 1}"}
        out_row = {"sr": f"OUT{i + 1}"}

        for _date in dates:
            date_str = format_date(_date)
            in_row[date_str] = ""
            out_row[date_str] = ""
        paired_rows.append(in_row)
        paired_rows.append(out_row)

    hours_worked_row = {"sr": "H Work"}
    extra_hours_worked_row = {"sr": "E Work"}
    processed_status_row = {"sr": "P Status"}
    status_row = {"sr": "Status"}
    shift_row = {"sr": "Shift"}
    return paired_rows, hours_worked_row, extra_hours_worked_row, processed_status_row, status_row, shift_row


def get_logs(employee_checkins):
    data = {"IN": [], "OUT": []}
    for checkin in employee_checkins:
        log_type = getattr(checkin, "log_type", "") or ""
        if log_type not in data:
            continue
        data[log_type].append(checkin)
    return data


@redis_cache
def get_shifts():
    return frappe.get_all("Shift Type", fields=["*"])


def get_status(employee, date, data_on_date, day_status, attendance_requests_map=None):
    status = day_status
    date = getdate(date)
    attendance = data_on_date.get("attendance", [])
    if attendance:
        attendance = attendance[0]
    checkins = data_on_date.get("checkins", [])
    leave_application_doc = None
    leave_type_doc = None

    if attendance:
        if attendance.leave_application and attendance.leave_type:
            leave_type_doc = frappe.get_cached_doc("Leave Type", attendance.leave_type)
            leave_application_doc = frappe.get_cached_doc("Leave Application", attendance.leave_application)

            leave_from_date = getdate(leave_application_doc.from_date)
            leave_to_date = getdate(leave_application_doc.to_date)

            is_lwp = leave_type_doc.is_lwp
            is_earned = leave_type_doc.is_earned_leave
            is_compensatory = leave_type_doc.is_compensatory

            if leave_from_date <= date <= leave_to_date:
                if is_lwp:
                    status = "LW"
                    if leave_application_doc.half_day_date == date and len(checkins) > 0:
                        status = "HLW"
                    lwp_counterpart = get_lwp_half_day_counterpart(
                        employee, date, leave_application_doc, attendance_requests_map
                    )
                    if lwp_counterpart:
                        status = lwp_counterpart.get("status") or status

                if is_compensatory:
                    status = "CO"
                    if leave_application_doc.half_day_date == date:
                        status = "HCO"

                if is_earned:
                    status = "EL"
                    if leave_application_doc.half_day_date == date:
                        status = "HEL"

                if "casual leave" in leave_type_doc.name.lower():
                    status = "CL"
                    if leave_application_doc.half_day_date == date:
                        status = "HCL"

                full_day_code = get_full_day_code_if_other_half_leave_approved(
                    employee, date, leave_application_doc, leave_type_doc
                )
                if full_day_code:
                    status = full_day_code
                else:
                    combo_status = get_half_day_combo_status(employee, date, leave_application_doc, leave_type_doc)
                    if combo_status:
                        status = combo_status

        if attendance.attendance_request:
            status = "OD"
            attendance_request = frappe.get_cached_doc("Attendance Request", attendance.attendance_request)
            if attendance_request.half_day_date == date:
                if attendance_requests_map and has_full_day_official_request(
                    attendance_requests_map, employee, date
                ):
                    status = "OD"
                else:
                    status = "HOD"
                    if attendance.leave_application:
                        if attendance.custom_attendance_tag == "EL":
                            status = "ODEL"
                        elif attendance.custom_attendance_tag == "CL":
                            status = "ODCL"
                        elif attendance.custom_attendance_tag == "CO":
                            status = "ODCO"

            if attendance_request.reason == "Mis Punch":
                status = "MIS"

        optional_status = get_optional_half_day_status(
            employee,
            date,
            attendance,
            leave_application_doc,
            leave_type_doc,
            checkins,
            status,
        )
        if optional_status:
            status = optional_status

    day_off_status = get_employee_day_off_status(employee, date, checkins, current_status=status)
    if day_off_status:
        status = day_off_status

    return status


def get_employee_day_off_status(employee: str, target_date, checkins=None, current_status=None):
    day_off_data = is_holiday_for_employee(employee, target_date)
    if not day_off_data or not day_off_data.get("is_holiday"):
        return None

    attendance_on_day_off = get_attendance_record(employee, target_date)
    has_checkins = bool(checkins)
    if attendance_on_day_off:
        tag = (attendance_on_day_off.get("custom_attendance_tag") or "").strip()
        if tag:
            half_day_leave_tag = get_half_day_leave_tag_for_day_off(attendance_on_day_off, target_date)
            if half_day_leave_tag:
                return half_day_leave_tag
            if tag in {"A", "A1"} and getattr(attendance_on_day_off, "custom_marked_absent_by_sandwich", 0):
                return "A1"
            if tag == "WO" and day_off_data.get("is_weekly_off") and has_checkins:
                return "POW"
            if tag == "HO" and not day_off_data.get("is_weekly_off") and has_checkins:
                return "POH"
            # An approved Official/Tour half-day request combined with a leave
            # half already produced a richer combo status upstream (e.g.
            # "ODCL"). custom_attendance_tag only ever stores the bare leave
            # code, so falling back to it here would silently drop the OD
            # half just because the day also happens to be a holiday/weekly-off.
            od_combo_map = {"EL": "ODEL", "CL": "ODCL", "CO": "ODCO"}
            if current_status and current_status.strip().upper() == od_combo_map.get(tag.upper()):
                return current_status
            return tag
        if getattr(attendance_on_day_off, "custom_marked_absent_by_sandwich", 0):
            return "A1"
    od_status = get_day_off_attendance_request_status(employee, target_date)
    if od_status:
        return od_status

    sandwich_status = get_sandwich_absent_status(employee, target_date, checkins=checkins)
    if sandwich_status:
        return sandwich_status

    if day_off_data.get("is_weekly_off"):
        return "POW" if has_checkins else "WO"

    return "POH" if has_checkins else "HO"


def get_half_day_leave_tag_for_day_off(attendance_on_day_off, target_date):
    if not attendance_on_day_off:
        return None

    attendance_status = cstr(attendance_on_day_off.get("status")).strip().lower()
    if attendance_status != "half day":
        return None

    leave_application_name = attendance_on_day_off.get("leave_application")
    if not leave_application_name:
        return None

    leave_application = frappe.get_cached_doc("Leave Application", leave_application_name)
    if not getattr(leave_application, "half_day", False):
        return None

    half_day_date = getattr(leave_application, "half_day_date", None)
    if not half_day_date or getdate(half_day_date) != getdate(target_date):
        return None

    tag = cstr(attendance_on_day_off.get("custom_attendance_tag")).strip().upper()
    mapping = {"CL": "HCL", "EL": "HEL", "CO": "HCO", "LW": "HLW", "LWP": "HLW"}
    return mapping.get(tag)


def get_day_off_attendance_request_status(employee: str, target_date):
    requests = frappe.get_all(
        "Attendance Request",
        filters={
            "employee": employee,
            "docstatus": ["=", 1],
            "from_date": ["<=", target_date],
            "to_date": [">=", target_date],
        },
        fields=["half_day", "half_day_date", "reason"],
    )

    for request in requests:
        reason = (request.get("reason") or "").strip().lower()
        if reason not in {"official", "tour"}:
            continue

        if request.get("half_day"):
            half_day_date = request.get("half_day_date")
            if half_day_date and getdate(half_day_date) == target_date:
                return "OD"
            continue

        return "OD"

    return None


def get_sandwich_absent_status(employee: str, target_date, checkins=None):
    # If there is physical presence on the day off, don't mark it as sandwich-absent.
    if checkins:
        return None

    attendance = get_attendance_record(employee, target_date)
    if attendance and getattr(attendance, "custom_marked_absent_by_sandwich", 0):
        return "A1"

    previous_attendance = get_attendance_record(employee, add_days(target_date, -1))
    next_attendance = get_attendance_record(employee, add_days(target_date, 1))

    def _is_sandwich_side(att):
        if not att:
            return False
        if getattr(att, "custom_marked_absent_by_sandwich", 0):
            return True

    # Treat the day-off as sandwich-absent when adjacent days indicate absence/leave.
    if _is_sandwich_side(previous_attendance) and _is_sandwich_side(next_attendance):
        return "A1"

    return None


def get_attendance_record(employee: str, target_date):
    records = frappe.get_all(
        "Attendance",
        filters={
            "employee": employee,
            "attendance_date": target_date,
            "docstatus": ["!=", 2],
        },
        fields=[
            "name",
            "status",
            "leave_type",
            "leave_application",
            "custom_attendance_tag",
            "custom_marked_absent_by_sandwich",
        ],
        limit=1,
    )
    return records[0] if records else None


def get_leave_code(leave_type_doc):
    if not leave_type_doc:
        return None
    if leave_type_doc.is_earned_leave:
        return "EL"
    if leave_type_doc.is_compensatory:
        return "CO"
    if leave_type_doc.is_lwp:
        return "LW"
    if "casual leave" in leave_type_doc.name.lower():
        return "CL"
    return None


def is_approved_leave_application(leave_application):
    if not leave_application:
        return False

    if isinstance(leave_application, dict):
        status = leave_application.get("status")
        docstatus = leave_application.get("docstatus")
    else:
        status = getattr(leave_application, "status", None)
        docstatus = getattr(leave_application, "docstatus", None)

    return (cstr(status).strip().lower() == "approved") and cint(docstatus) == 1


def get_approved_half_day_leave_applications(employee, target_date, exclude_name=None):
    if not employee or not target_date:
        return []

    filters = {
        "employee": employee,
        "status": "Approved",
        "docstatus": 1,
        "from_date": ["<=", target_date],
        "to_date": [">=", target_date],
        "half_day": 1,
        "half_day_date": target_date,
    }
    if exclude_name:
        filters["name"] = ["!=", exclude_name]

    leave_applications = frappe.get_all(
        "Leave Application",
        filters=filters,
        fields=["name", "leave_type", "custom_half_type", "status", "docstatus"],
    )

    return [leave for leave in leave_applications if is_approved_leave_application(leave)]


def get_full_day_code_if_other_half_leave_approved(employee, target_date, primary_application, primary_leave_type):
    if not employee or not target_date or not primary_application or not primary_leave_type:
        return None

    if not getattr(primary_application, "half_day", False):
        return None
    if not getattr(primary_application, "half_day_date", None):
        return None
    if getdate(primary_application.half_day_date) != target_date:
        return None

    primary_code = get_leave_code(primary_leave_type)
    if primary_code not in {"EL", "CL", "CO"}:
        return None

    primary_half_type = (getattr(primary_application, "custom_half_type", None) or "").strip()

    other_leaves = get_approved_half_day_leave_applications(employee, target_date, primary_application.name)

    for other in other_leaves:
        other_half_type = (getattr(other, "custom_half_type", None) or "").strip()
        if primary_half_type and other_half_type and other_half_type == primary_half_type:
            continue

        other_leave_type = frappe.get_cached_doc("Leave Type", other.leave_type)
        other_code = get_leave_code(other_leave_type)
        if other_code == primary_code:
            return primary_code

    return None


def get_half_day_combo_status(employee, target_date, primary_application, primary_leave_type):
    if not primary_application or not primary_leave_type:
        return None
    if not primary_application.half_day_date:
        return None
    if getdate(primary_application.half_day_date) != target_date:
        return None

    primary_code = get_leave_code(primary_leave_type)
    if primary_code not in {"EL", "CO", "CL"}:
        return None

    other_half_leaves = get_approved_half_day_leave_applications(employee, target_date, primary_application.name)

    for other in other_half_leaves:
        other_leave_type = frappe.get_cached_doc("Leave Type", other.leave_type)
        other_code = get_leave_code(other_leave_type)
        if not other_code:
            continue
        codes = {primary_code, other_code}
        if codes == {"EL", "CO"}:
            return "ELCO"
        if codes == {"CL", "CO"}:
            return "CLCO"

    return None


def get_lwp_half_day_counterpart_for_attendance(
    employee, target_date, attendance_doc, attendance_requests_map=None
):
    if not attendance_doc or not attendance_doc.get("leave_application") or not attendance_doc.get("leave_type"):
        return None

    leave_type_doc = frappe.get_cached_doc("Leave Type", attendance_doc.get("leave_type"))
    if not leave_type_doc or not leave_type_doc.is_lwp:
        return None

    leave_application_doc = frappe.get_cached_doc("Leave Application", attendance_doc.get("leave_application"))
    return get_lwp_half_day_counterpart(
        employee,
        target_date,
        leave_application_doc,
        attendance_requests_map,
    )


def get_lwp_half_day_counterpart(employee, target_date, lwp_application, attendance_requests_map=None):
    if not employee or not target_date or not lwp_application:
        return None
    if not getattr(lwp_application, "half_day", False):
        return None

    half_day_date = getattr(lwp_application, "half_day_date", None)
    if not half_day_date or getdate(half_day_date) != target_date:
        return None

    lwp_half_type = (getattr(lwp_application, "custom_half_type", None) or "").strip()
    other_leaves = get_approved_half_day_leave_applications(
        employee, target_date, getattr(lwp_application, "name", None)
    )
    for other in other_leaves:
        other_half_type = (getattr(other, "custom_half_type", None) or "").strip()
        if lwp_half_type and other_half_type and other_half_type == lwp_half_type:
            continue

        other_leave_type = frappe.get_cached_doc("Leave Type", other.leave_type)
        other_code = get_leave_code(other_leave_type)
        if other_code in {"CL", "EL", "CO"}:
            return {
                "status": f"H{other_code}",
                "half_type": other_half_type,
                "source": "Leave Application",
                "name": other.name,
            }

    attendance_request = get_lwp_half_day_attendance_request_counterpart(
        employee, target_date, lwp_half_type, attendance_requests_map
    )
    if attendance_request:
        return {
            "status": "HOD",
            "half_type": (attendance_request.get("custom_half_type") or "").strip(),
            "source": "Attendance Request",
            "name": attendance_request.get("name"),
        }

    return None


def get_lwp_half_day_attendance_request_counterpart(
    employee, target_date, lwp_half_type=None, attendance_requests_map=None
):
    requests_on_date = []
    if attendance_requests_map:
        requests_on_date = attendance_requests_map.get(employee, {}).get(format_date(target_date), []) or []

    if not requests_on_date:
        requests_on_date = frappe.get_all(
            "Attendance Request",
            filters={
                "employee": employee,
                "docstatus": 1,
                "from_date": ["<=", target_date],
                "to_date": [">=", target_date],
                "half_day": 1,
                "half_day_date": target_date,
            },
            fields=["name", "reason", "half_day", "half_day_date", "custom_half_type", "docstatus"],
        )

    for request in requests_on_date:
        reason = (request.get("reason") or "").strip().lower()
        if reason not in {"official", "tour"}:
            continue

        request_docstatus = request.get("docstatus")
        if request_docstatus is None and request.get("name"):
            request_docstatus = frappe.get_cached_value("Attendance Request", request.get("name"), "docstatus")
        if cint(request_docstatus) != 1:
            continue
        if not request.get("half_day"):
            continue
        request_half_day_date = request.get("half_day_date")
        if not request_half_day_date or getdate(request_half_day_date) != target_date:
            continue

        request_half_type = (request.get("custom_half_type") or "").strip()
        if lwp_half_type and request_half_type and request_half_type == lwp_half_type:
            continue
        return request

    return None


def is_optional_leave_type(leave_type_doc_or_name):
    if not leave_type_doc_or_name:
        return False
    if isinstance(leave_type_doc_or_name, str):
        return bool(frappe.get_cached_value("Leave Type", leave_type_doc_or_name, "is_optional_leave"))
    return bool(getattr(leave_type_doc_or_name, "is_optional_leave", False))


def get_optional_half_day_status(
    employee,
    target_date,
    attendance_doc,
    leave_application_doc,
    leave_type_doc,
    checkins,
    current_status,
):
    if not attendance_doc or not leave_application_doc or not leave_type_doc:
        return None
    if not is_optional_leave_type(leave_type_doc):
        return None
    if not getattr(leave_application_doc, "half_day", False):
        return None
    half_day_date = getattr(leave_application_doc, "half_day_date", None)
    if not half_day_date or getdate(half_day_date) != target_date:
        return None
    attendance_status = (getattr(attendance_doc, "status", "") or "").lower()
    if attendance_status != "half day":
        return None

    other_combo = get_optional_combo_from_other_leave(employee, target_date, leave_application_doc.name)
    if other_combo:
        return other_combo

    request_combo = get_optional_combo_from_attendance_request(attendance_doc, target_date)
    if request_combo:
        return request_combo

    status_combo = get_optional_combo_from_status(current_status)
    if status_combo:
        return status_combo

    if checkins:
        return "PHO"

    return "HHO"


def get_optional_combo_from_other_leave(employee, target_date, primary_application_name):
    if not primary_application_name:
        return None

    other_half_leaves = get_approved_half_day_leave_applications(employee, target_date, primary_application_name)

    mapping = {"EL": "ELHO", "CL": "CLHO", "CO": "COHO", "LW": "LWHO"}
    for other in other_half_leaves:
        other_leave_type = frappe.get_cached_doc("Leave Type", other.leave_type)
        if is_optional_leave_type(other_leave_type):
            continue
        other_code = get_leave_code(other_leave_type)
        if other_code in mapping:
            return mapping[other_code]

    return None


def get_optional_combo_from_attendance_request(attendance_doc, target_date):
    if not attendance_doc or not attendance_doc.attendance_request:
        return None

    attendance_request = frappe.get_cached_doc("Attendance Request", attendance_doc.attendance_request)
    if not getattr(attendance_request, "half_day", False):
        return None
    half_day_date = getattr(attendance_request, "half_day_date", None)
    if not half_day_date or getdate(half_day_date) != target_date:
        return None

    if attendance_request.reason == "Mis Punch":
        return "PHO"

    return "ODHO"


def get_optional_combo_from_status(current_status):
    if not current_status:
        return None

    status_map = {
        "HEL": "ELHO",
        "HCL": "CLHO",
        "HCO": "COHO",
        "HLW": "LWHO",
        "HOD": "ODHO",
        "MIS": "MHO",
    }
    return status_map.get(current_status)


@redis_cache
def has_short_leave(employee, for_date):
    if not employee or not for_date:
        return False
    try:
        for_date = getdate(for_date)
    except Exception:
        return False
    return bool(
        frappe.db.exists(
            "Short Leave",
            {
                "employee": employee,
                "for_date": for_date,
                "docstatus": 1,
            },
        )
    )


def _get_employee_and_date_for_short_leave(attendance_doc, checkins):
    employee = None
    for_date = None

    if attendance_doc:
        try:
            employee = attendance_doc.get("employee")
            for_date = attendance_doc.get("attendance_date")
        except Exception:
            employee = getattr(attendance_doc, "employee", None)
            for_date = getattr(attendance_doc, "attendance_date", None)

    if (not employee or not for_date) and checkins:
        first = checkins[0]
        try:
            employee = employee or first.get("employee")
            for_date = for_date or first.get("shift_start") or first.get("time")
        except Exception:
            employee = employee or getattr(first, "employee", None)
            for_date = for_date or getattr(first, "shift_start", None) or getattr(first, "time", None)

    if not employee or not for_date:
        return None, None

    return employee, getdate(for_date)


def derive_processed_status(
    status_code,
    processed_code,
    attendance_doc,
    checkins,
    worked_hours,
    holiday_info,
    employee=None,
    target_date=None,
    attendance_requests_map=None,
):
    display_status = (status_code or "").strip()
    business_status = (processed_code or "").strip()
    primary_status = business_status or display_status
    presence = _has_physical_presence(worked_hours, checkins)
    holiday_info = holiday_info if isinstance(holiday_info, dict) else {}
    is_day_off = bool(holiday_info.get("is_holiday"))

    # If employee is present and has an approved Short Leave on the same day,
    # show processed status as SL in reports.
    if display_status == "P":
        employee, for_date = _get_employee_and_date_for_short_leave(attendance_doc, checkins)
        if employee and for_date and has_short_leave(employee, for_date):
            return "SL"

    direct_map = {
        "LW": "A",
        "LWP": "A",
        "HLW": "PLW",
    }
    if primary_status in direct_map:
        return direct_map[primary_status]

    if primary_status == "OD":
        return "WO" if is_day_off else "OD"

    if primary_status == "HOD":
        if is_day_off:
            return "WO"
        if checkins:
            return "POD"
        if display_status == "MIS":
            return "POD"
        return "HOD"

    if primary_status in {"HCL", "HEL", "HCO"}:
        return _map_half_day_leave_presence(
            primary_status,
            attendance_doc,
            checkins,
            worked_hours,
        )

    if primary_status == "MIS":
        return _derive_mis_processed_status(
            attendance_doc, presence, employee, target_date, attendance_requests_map
        )

    return business_status or display_status


def _map_half_day_leave_presence(status_code, attendance_doc, checkins, worked_hours):
    mapping = {"HCL": "PCL", "HEL": "PEL", "HCO": "PCO"}
    if _has_half_day_qualifying_presence(attendance_doc, checkins, worked_hours) and status_code in mapping:
        return mapping[status_code]
    return status_code


def _has_confirmed_presence(worked_hours, checkins):
    if worked_hours and worked_hours > 0:
        return True
    return bool(checkins and len(checkins) >= 2)


def _has_half_day_qualifying_presence(attendance_doc, checkins, worked_hours):
    threshold_hours = _get_half_day_threshold_hours(attendance_doc, checkins)
    effective_hours = worked_hours or _calculate_hours_from_checkins(checkins)

    if threshold_hours is not None:
        return bool(effective_hours and effective_hours >= threshold_hours)

    return _has_confirmed_presence(worked_hours, checkins)


def _get_half_day_threshold_hours(attendance_doc, checkins):
    shift_name = None
    if attendance_doc:
        try:
            shift_name = attendance_doc.get("shift")
        except AttributeError:
            shift_name = getattr(attendance_doc, "shift", None)

    if not shift_name and checkins:
        shift_name = checkins[0].get("shift")

    if not shift_name:
        return None

    raw_threshold = frappe.get_cached_value("Shift Type", shift_name, "custom_working_hours_threshold_for_half_day")
    if not raw_threshold:
        raw_threshold = frappe.get_cached_value("Shift Type", shift_name, "custom_half_day_threshold")

    threshold_hours = convert_time_to_hours(raw_threshold)
    return threshold_hours if threshold_hours else None


def _has_physical_presence(worked_hours, checkins):
    # if worked_hours and worked_hours > 0:
    #     return True
    return bool(checkins)


def _derive_mis_processed_status(
    attendance_doc, presence, employee=None, target_date=None, attendance_requests_map=None
):
    if not attendance_doc:
        return "MIS"
    request_doc = _get_attendance_request_doc(attendance_doc.get("attendance_request"))
    leave_code = _get_leave_code_from_attendance(attendance_doc)
    request_reason = (request_doc.reason or "").strip().lower() if request_doc else ""
    request_half_day = bool(getattr(request_doc, "half_day", False) or attendance_doc.get("half_day"))

    if request_doc and request_reason == "mis punch":
        if request_half_day:
            combo = _map_leave_code_combo(leave_code)
            if combo:
                return combo
            # The other half may be covered by its own approved Official/Tour
            # request even though only this Mis Punch request is linked on the
            # Attendance record (Attendance can only store one linked request,
            # so a second half-day request silently displaces the first one).
            other_half_request = get_complementary_official_half_request(
                attendance_requests_map,
                employee,
                target_date,
                getattr(request_doc, "custom_half_type", None),
            )
            if other_half_request:
                return "POD"
            return "HD"
        return "P"

    if request_doc and request_half_day and request_reason in {"official", "tour"}:
        return "POD"

    if leave_code and presence:
        combo = _map_leave_code_combo(leave_code)
        if combo:
            return combo

    return "MIS"


def get_complementary_official_half_request(
    attendance_requests_map, employee, target_date, exclude_half_type=None
):
    """Find an approved Official/Tour half-day request covering the other half of the day.

    Attendance only stores a single ``attendance_request`` link, so when two
    half-day requests exist for the same date (e.g. Tour for the first half,
    Mis Punch for the second), only one survives on the Attendance record.
    This looks at every request for the date instead of just the linked one.
    """
    if not attendance_requests_map or not employee or not target_date:
        return None

    requests_on_date = attendance_requests_map.get(employee, {}).get(format_date(target_date), [])
    exclude_half_type = (exclude_half_type or "").strip().lower()

    for request in requests_on_date:
        if not request.get("half_day"):
            continue
        reason = (request.get("reason") or "").strip().lower()
        if reason not in {"official", "tour"}:
            continue
        half_type = (request.get("custom_half_type") or "").strip().lower()
        if exclude_half_type and half_type == exclude_half_type:
            continue
        return request

    return None


def _map_leave_code_combo(leave_code):
    mapping = {"EL": "PEL", "CL": "PCL", "CO": "PCO", "LW": "PLW", "LWP": "PLW"}
    return mapping.get(leave_code)


def _get_attendance_request_doc(request_name):
    if not request_name:
        return None
    try:
        return frappe.get_cached_doc("Attendance Request", request_name)
    except frappe.DoesNotExistError:
        return None


def _get_leave_code_from_attendance(attendance_doc):
    if not attendance_doc or not attendance_doc.get("leave_type"):
        return None
    try:
        leave_type_doc = frappe.get_cached_doc("Leave Type", attendance_doc.get("leave_type"))
    except frappe.DoesNotExistError:
        return None
    return get_leave_code(leave_type_doc)


def adjust_status_with_checkins(processed_status, checkins, shift_name, shift_map):
    GENERIC_STATUS_CODES = {"", "A", "P", "HD", "MIS"}
    base_status = processed_status or ""
    if base_status == "MIS":
        return "MIS"
    if not checkins:
        if base_status and base_status not in GENERIC_STATUS_CODES:
            return base_status
        return "A"

    if len(checkins) == 1:
        if base_status and base_status not in GENERIC_STATUS_CODES:
            return base_status
        return "MIS"

    shift_doc = _resolve_shift_document(shift_name, checkins, shift_map)
    if not shift_doc:
        return base_status

    if base_status and base_status not in GENERIC_STATUS_CODES:
        return base_status

    worked_hours = _calculate_hours_from_checkins(checkins)
    if worked_hours == 0:
        return base_status or "A"

    derived_status = _determine_status_from_hours(worked_hours, shift_doc)
    return derived_status or base_status


def _resolve_shift_document(explicit_shift_name, checkins, shift_map):
    candidates = [explicit_shift_name]
    if checkins:
        first_checkin = checkins[0]
        candidates.append(first_checkin.get("shift"))

    for candidate in candidates:
        if candidate and candidate in shift_map:
            return shift_map[candidate]
    return None


def _calculate_hours_from_checkins(checkins):
    logs = get_logs(checkins)
    in_logs = logs.get("IN") or []
    out_logs = logs.get("OUT") or []
    total_seconds = 0.0

    pairable_entries = min(len(in_logs), len(out_logs))
    for idx in range(pairable_entries):
        in_time = get_datetime(in_logs[idx].get("time")) if in_logs[idx].get("time") else None
        out_time = get_datetime(out_logs[idx].get("time")) if out_logs[idx].get("time") else None
        if not in_time or not out_time:
            continue

        delta = out_time - in_time
        if delta.total_seconds() > 0:
            total_seconds += delta.total_seconds()

    return total_seconds / 3600 if total_seconds else 0.0


def get_holiday_extra_work(checkins):
    if len(checkins) < 2:
        return ""

    in_time = get_datetime(checkins[0].get("time")) if checkins[0].get("time") else None
    out_time = get_datetime(checkins[-1].get("time")) if checkins[-1].get("time") else None
    if not in_time or not out_time:
        return ""

    delta = out_time - in_time
    if delta.total_seconds() <= 0:
        return ""

    return format_time_hhmm(delta)


def _determine_status_from_hours(worked_hours, shift_doc):
    present_threshold = convert_time_to_hours(
        shift_doc.get("custom_working_hours_threshold_for_present")
        or shift_doc.get("custom_shift_time")
        or shift_doc.get("shift_hours")
    )
    half_day_threshold = convert_time_to_hours(shift_doc.get("custom_working_hours_threshold_for_half_day"))
    absent_threshold = convert_time_to_hours(shift_doc.get("custom_working_hours_threshold_for_absent"))

    if not half_day_threshold and present_threshold:
        half_day_threshold = present_threshold / 2
    if not absent_threshold and half_day_threshold:
        absent_threshold = half_day_threshold / 2

    if present_threshold and worked_hours >= present_threshold:
        return "P"
    if half_day_threshold and worked_hours >= half_day_threshold:
        return "HD"
    if absent_threshold and worked_hours < absent_threshold:
        return "A"
    if present_threshold or half_day_threshold or absent_threshold:
        return "A"
    return None


def format_time_hhmm(value):
    if not value:
        return ""
    if isinstance(value, timedelta):
        total_seconds = int(value.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes = remainder // 60
        return f"{hours:02d}:{minutes:02d}"
    if isinstance(value, datetime):
        value = value.time()
    if isinstance(value, dt_time):
        return value.strftime("%H:%M")
    try:
        parsed = get_time(value)
        if isinstance(parsed, dt_time):
            return parsed.strftime("%H:%M")
    except Exception:
        pass
    return str(value)
