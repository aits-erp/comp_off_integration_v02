# Copyright (c) 2025, rtCamp and contributors
# For license information, please see license.txt
from datetime import date, datetime, timedelta
from datetime import time as dt_time
from importlib import import_module

import frappe
from frappe.utils import add_days, cint, format_date, get_time

from real_group_hrms.utils import is_holiday_for_employee

day_wise_attendance = import_module("real_group_hrms.real_group.report.[new]_day_wise_attendance.[new]_day_wise_attendance")

column_config = [
    {"fieldname": "present", "label": "P", "metric": "present"},
    {"fieldname": "absent", "label": "A", "metric": "absent"},
    {"fieldname": "weekly_off", "label": "WO", "metric": "weekly_off"},
    {"fieldname": "holiday", "label": "HO", "metric": "holiday"},
    {"fieldname": "half_day", "label": "Half", "metric": "half_day"},
    {"fieldname": "od", "label": "OD", "metric": "od"},
    {"fieldname": "tour", "label": "Tour", "metric": "tour"},
    {"fieldname": "cl", "label": "CL", "metric": "cl"},
    {"fieldname": "el", "label": "EL", "metric": "el"},
    {"fieldname": "co", "label": "CO", "metric": "co"},
    {"fieldname": "paid_days", "label": "Paid Days", "metric": "paid_days"},
    {"fieldname": "late", "label": "Late", "metric": "late"},
]

fieldnames = [column["fieldname"] for column in column_config]

leave_split = {
    "P": {"present": 1},
    "SL": {"present": 1},
    "POW": {"present": 1},
    "POH": {"present": 1},
    "PEL": {"present": 0.5, "el": 0.5, "half_day": 1.0},
    "PCL": {"present": 0.5, "cl": 0.5, "half_day": 1.0},
    "PCO": {"present": 0.5, "co": 0.5, "half_day": 1.0},
    "POD": {"present": 0.5, "od": 0.5, "half_day": 1.0},
    "PLW": {"present": 0.5, "absent": 0.5, "half_day": 1.0},
    "PHO": {"present": 0.5, "holiday": 0.5, "half_day": 1.0},
    "A": {"absent": 1},
    "A1": {"absent": 1},
    "MIS": {"absent": 1},
    "HD": {"present": 0.5, "absent": 0.5, "half_day": 1.0},
    "LW": {"absent": 1},
    "LWP": {"absent": 1},
    "WO": {"weekly_off": 1},
    "HO": {"holiday": 1},
    "HHO": {"holiday": 0.5, "absent": 0.5, "half_day": 1.0},
    "MHO": {"absent": 0.5, "holiday": 0.5, "half_day": 1.0},
    "EL": {"el": 1},
    "HEL": {"el": 0.5, "absent": 0.5, "half_day": 1.0},
    "ELHO": {"el": 0.5, "holiday": 0.5, "half_day": 1.0},
    "ELCO": {"el": 0.5, "co": 0.5, "half_day": 1.0},
    "CL": {"cl": 1},
    "HCL": {"cl": 0.5, "absent": 0.5, "half_day": 1.0},
    "CLHO": {"cl": 0.5, "holiday": 0.5, "half_day": 1.0},
    "CLCO": {"cl": 0.5, "co": 0.5, "half_day": 1.0},
    "CO": {"co": 1},
    "HCO": {"co": 0.5, "absent": 0.5, "half_day": 1.0},
    "COHO": {"co": 0.5, "holiday": 0.5, "half_day": 1.0},
    "LWHO": {"absent": 0.5, "holiday": 0.5, "half_day": 1.0},
    "OD": {"od": 1},
    "HOD": {"od": 0.5, "absent": 0.5, "half_day": 1.0},
    "ODEL": {"od": 0.5, "el": 0.5, "half_day": 1.0},
    "ODCL": {"od": 0.5, "cl": 0.5, "half_day": 1.0},
    "ODCO": {"od": 0.5, "co": 0.5, "half_day": 1.0},
    "ODHO": {"od": 0.5, "holiday": 0.5, "half_day": 1.0},
}


def execute(filters=None):
    month = filters.get("month")
    year = cint(filters.get("year"))
    include_processed_status = bool(cint(filters.get("processed_attendance")))
    all_company = bool(cint(filters.get("all_company")))
    columns = day_wise_attendance.get_columns(month, year)
    append_summary_columns(columns)
    data = []
    company = filters.get("company")
    branch = filters.get("branch")
    division = filters.get("division")
    department = filters.get("department")
    employee = filters.get("employee")
    dates = day_wise_attendance.get_dates(month, year)
    effective_end_date = min(dates[-1], frappe.utils.getdate())
    employees = get_employees(company, branch, division, department, employee, dates[0], dates[-1], all_company)
    employee_names = [emp.name for emp in employees]
    attendance_map = day_wise_attendance.get_attendance(employee_names, dates[0], dates[-1], month, year)
    attendance_requests_map = day_wise_attendance.get_attendance_requests(employee_names, dates[0], dates[-1])
    shifts = day_wise_attendance.get_shifts()
    shift_map = {shift.name: shift for shift in shifts}
    for employee in employees:
        info = {"sr": "PAYCODE, CARD NO. & NAME"}

        emp_data = attendance_map.get(employee.name, {})
        max_checkins = emp_data.get("max_checkins", 0)

        max_pairs = 0
        pairs = ((max_checkins) + 1) // 2
        max_pairs = max(max_pairs, pairs)

        (row_keys, hours_worked, extra_worked, processed_status, status, shift) = day_wise_attendance.get_rows(
            max_pairs, dates
        )
        hours_worked = {"sr": "N Work"}
        total_hours = 0.0

        for _date in dates:
            date_str = format_date(_date)
            if _date > effective_end_date or day_wise_attendance.is_outside_service_period(employee, _date):
                status[date_str] = None
                processed_status[date_str] = None
                shift[date_str] = None
                continue

            emp_date_data = emp_data.get(date_str, {})
            checkins_on_date = emp_date_data.get("checkins", [])
            emp_checkins = sorted(checkins_on_date, key=lambda x: x.time)
            in_out_logs = day_wise_attendance.get_logs(emp_checkins)
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
                        extra_worked[date_str] = format_time_hhmm(worked_time)
                    else:
                        dt1 = datetime.combine(date.today(), shift_time)
                        dt2 = datetime.combine(date.today(), worked_time)
                        delta = dt2 - dt1
                        if delta.total_seconds() > 0:
                            extra_worked[date_str] = format_time_hhmm(delta)
                if shift_type and shift_type.custom_shift_time and not worked_hours_value:
                    if holiday_info and holiday_info.get("is_holiday"):
                        holiday_extra_work = day_wise_attendance.get_holiday_extra_work(emp_checkins)
                        if holiday_extra_work:
                            extra_worked[date_str] = holiday_extra_work
            processed_value = day_wise_attendance.get_status(
                employee.name, _date, emp_date_data, day_status, attendance_requests_map
            )
            status_value = day_wise_attendance.adjust_status_with_checkins(
                processed_value, emp_checkins, day_shift_name, shift_map
            )
            if day_wise_attendance.has_mis_punch_request(
                attendance_requests_map, employee.name, _date
            ):  # if theres mispunch status should be mispunch
                status_value = "MIS"
            status[date_str] = status_value
            attendance_doc = attendance_on_date[0] if attendance_on_date else None
            processed_status[date_str] = day_wise_attendance.derive_processed_status(
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
        summary_dates = []
        temp_date = dates[0]
        for _ in range(8):
            summary_dates.append(format_date(temp_date))
            temp_date = add_days(temp_date, days=1)

        counted_dates = [_date for _date in dates if _date <= effective_end_date]
        summary_metrics = calculate_summary_metrics(processed_status, emp_data, counted_dates)

        if len(summary_dates) >= 8:
            total_time = timedelta(seconds=round(total_hours * 3600 / 60) * 60)
            info[summary_dates[0]] = employee["name"]
            info[summary_dates[1]] = employee["employee_name"]
            info[summary_dates[2]] = employee.get("designation", "")
            info[summary_dates[3]] = employee.get("department", "")
            info[summary_dates[4]] = f"Present: {format_summary_value(summary_metrics.get('present', 0.0))}"
            info[summary_dates[5]] = f"Absent: {format_summary_value(summary_metrics.get('absent', 0.0))}"
            info[summary_dates[6]] = f"Hours: {format_time_hhmm(total_time)}"

        apply_summary_metrics(shift, summary_metrics)
        data.append(info)
        data.extend(row_keys)
        data.append(hours_worked)
        if include_processed_status:
            data.append(processed_status)
        data.append(shift)

    return columns, data


def get_employees(
    company,
    branch,
    division=None,
    department=None,
    employee=None,
    start_date=None,
    end_date=None,
    all_company=False,
):
    if not all_company and not company:
        return []

    filters = {"branch": branch, "status": ["in", ["Active", "Left"]]}
    if not all_company and company:
        filters["company"] = company
    if division:
        filters["custom_division"] = division
    if department:
        filters["department"] = department
    if employee:
        filters["name"] = employee

    employees = frappe.get_all("Employee", filters=filters, fields=["*"])
    employees = day_wise_attendance.filter_employees_for_period(employees, start_date, end_date)
    return sorted(employees, key=day_wise_attendance.get_employee_sort_key)


def append_summary_columns(columns):
    for column in column_config:
        columns.append(
            {
                "fieldname": column["fieldname"],
                "fieldtype": "Data",
                "label": column["label"],
                "width": 70,
            }
        )


def calculate_summary_metrics(status_row, emp_data, dates):
    FULL_PAID_STATUSES = {
        "P",
        "SL",
        "POH",
        "POW",
        "CL",
        "EL",
        "CO",
        "PEL",
        "PCL",
        "PCO",
        "PHO",
        "POD",
        "OD",
        "HO",
        "WO",
        "ELCO",
        "CLCO",
        "ODCL",
        "ODEL",
        "ODCO",
        "ELHO",
        "CLHO",
        "COHO",
        "ODHO",
        "MHO",
    }
    HALF_PAID_STATUSES = {"HD", "HCL", "HEL", "HCO", "HOD", "PLW", "HHO", "LWHO", "PHO"}
    metrics = {column["metric"]: 0.0 for column in column_config}
    paid_days = 0.0
    for _date in dates:
        date_key = format_date(_date)
        attendance_documents = (emp_data.get(date_key) or {}).get("attendance") or []
        status_code = (status_row.get(date_key) or "").strip().upper()
        contributions = leave_split.get(status_code, {})
        for metric_key, value in contributions.items():
            metrics[metric_key] = metrics.get(metric_key, 0.0) + value
        if status_code in FULL_PAID_STATUSES:
            paid_days += 1
        elif status_code in HALF_PAID_STATUSES:
            paid_days += 0.5
        if _has_late_entry(attendance_documents):
            metrics["late"] = metrics.get("late", 0.0) + 1
        tour_entries = _count_tour_attendance_requests(attendance_documents)
        if tour_entries:
            metrics["tour"] = metrics.get("tour", 0.0) + tour_entries

    metrics["paid_days"] = paid_days

    return metrics


def _has_late_entry(attendance_documents):
    if not attendance_documents:
        return False

    for document in attendance_documents:
        late_value = document.get("late_entry")
        try:
            if cint(late_value) == 1:
                return True
        except Exception:
            continue
    return False


def _count_tour_attendance_requests(attendance_documents):
    if not attendance_documents:
        return 0

    tour_count = 0
    for document in attendance_documents:
        attendance_request = document.get("attendance_request")
        if not attendance_request:
            continue
        try:
            reason = frappe.get_cached_value("Attendance Request", attendance_request, "reason")
        except Exception:
            continue
        if (reason or "").strip().lower() == "tour":
            half_day = frappe.get_cached_value("Attendance Request", attendance_request, "half_day")
            if half_day:
                tour_count += 0.5
            else:
                tour_count += 1
    return tour_count


def apply_summary_metrics(target_row, metrics):
    if not target_row:
        return

    for column in column_config:
        metric_key = column["metric"]
        value = metrics.get(metric_key, 0.0)
        if metric_key == "late":
            target_row[column["fieldname"]] = int(value) if value else 0
            continue
        target_row[column["fieldname"]] = format_summary_value(value)


def format_summary_value(value):
    numeric_value = float(value or 0)
    if not numeric_value:
        return 0
    rounded_value = round(numeric_value, 2)
    if rounded_value.is_integer():
        return int(rounded_value)
    return rounded_value


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
