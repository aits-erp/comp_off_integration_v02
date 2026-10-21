# Copyright (c) 2025, rtCamp and contributors
# For license information, please see license.txt

from importlib import import_module

from frappe.utils import cint

dw = import_module("real_group_hrms.real_group.report.[new]_day_wise_attendance.[new]_day_wise_attendance")
form = import_module("real_group_hrms.real_group.report.[new]_form_14.[new]_form_14")


def execute(filters=None):
    filters = filters or {}
    month = filters.get("month")
    year = cint(filters.get("year"))
    columns = build_columns()

    form_filters = dict(filters)
    form_filters.setdefault("processed_report", 1)
    _, raw_rows = form.execute(form_filters)

    first_half_rows = [row for row in (raw_rows or []) if row and row.get("sr")]

    result = []
    for row in first_half_rows:
        employee_id = row.get("token_no")
        present_total = row.get("p") or 0.0
        absent_total = row.get("a") or 0.0
        earned_leave_total = row.get("el") or 0.0
        casual_leave_total = row.get("cl") or 0.0
        od_total = row.get("od") or 0.0
        compensatory_off_total = row.get("co") or 0.0
        holiday_total = row.get("ho") or 0.0
        weekly_off_total = row.get("wo") or 0.0
        paid_days_total = calculate_paid_days(
            present=present_total,
            earned_leave=earned_leave_total,
            casual_leave=casual_leave_total,
            od=od_total,
            compensatory_off=compensatory_off_total,
            holiday=holiday_total,
            weekly_off=weekly_off_total,
        )

        result.append(
            {
                "employee": employee_id,
                "employee_name": row.get("employee_name"),
                "total_present": present_total,
                "total_absent": absent_total,
                "total_earned_leave": earned_leave_total,
                "total_casual_leave": casual_leave_total,
                "total_od": od_total,
                # Tour is intentionally disabled here for now.
                # form_14 already rolls tour into OD for this report flow.
                # "total_tour": 0.0,
                "total_compensatory_off": compensatory_off_total,
                "total_holiday_leave": holiday_total,
                "total_wo": weekly_off_total,
                "total_ttl": paid_days_total,
                "total_monthly_hours": row.get("m") or 0.0,
            }
        )

    return columns, result


def build_columns():
    columns = [
        {"fieldname": "employee", "fieldtype": "Data", "label": "Employee UID"},
        {"fieldname": "employee_name", "fieldtype": "Data", "label": "Employee Name"},
        {"fieldname": "total_present", "fieldtype": "Float", "default": 0, "label": "P"},
        {"fieldname": "total_absent", "fieldtype": "Float", "default": 0, "label": "A"},
        {"fieldname": "total_earned_leave", "fieldtype": "Float", "default": 0, "label": "EL"},
        {"fieldname": "total_casual_leave", "fieldtype": "Float", "default": 0, "label": "CL"},
        {"fieldname": "total_od", "fieldtype": "Float", "default": 0, "label": "OD"},
        # {"fieldname": "total_tour", "fieldtype": "Float", "default": 0, "label": "Tour"},
        {"fieldname": "total_compensatory_off", "fieldtype": "Float", "default": 0, "label": "CO"},
        {"fieldname": "total_holiday_leave", "fieldtype": "Float", "default": 0, "label": "HO"},
        {"fieldname": "total_wo", "fieldtype": "Float", "default": 0, "label": "WO"},
        {"fieldname": "total_ttl", "fieldtype": "Float", "default": 0, "label": "Paid Days"},
        {"fieldname": "total_monthly_hours", "fieldtype": "Float", "default": 0, "label": "Monthly Hours"},
    ]
    return columns


# Tour recomputation is intentionally disabled for now.
# This report should mirror form_14 values directly.
# def _is_holiday(employee: str, target_date: date) -> bool:
#     holiday_info = is_holiday_for_employee(employee, target_date)
#     return bool(holiday_info.get("is_holiday")) if isinstance(holiday_info, dict) else False
#
#
# def _get_request_day_value(request: dict) -> float:
#     if request.get("half_day"):
#         return 0.5
#     return 1.0
#
#
# def _compute_od_and_tour(employee: str, dates: list[date], request_map: dict) -> tuple[float, float]:
#     od_total = 0.0
#     tour_total = 0.0
#
#     employee_requests = request_map.get(employee) or {}
#     for target_date in dates:
#         if _is_holiday(employee, target_date):
#             continue
#
#         requests_on_date = employee_requests.get(dw.format_date(target_date), [])
#         for request in requests_on_date:
#             reason = (request.get("reason") or "").strip().lower()
#             if reason == "official":
#                 od_total += _get_request_day_value(request)
#             elif reason == "tour":
#                 tour_total += _get_request_day_value(request)
#
#     return od_total, tour_total


def calculate_paid_days(
    *,
    present: float,
    earned_leave: float,
    casual_leave: float,
    od: float,
    compensatory_off: float,
    holiday: float,
    weekly_off: float,
) -> float:
    paid_days = (
        float(present or 0)
        + float(earned_leave or 0)
        + float(casual_leave or 0)
        + float(od or 0)
        + float(compensatory_off or 0)
        + float(holiday or 0)
        + float(weekly_off or 0)
    )
    return round(paid_days, 2)
