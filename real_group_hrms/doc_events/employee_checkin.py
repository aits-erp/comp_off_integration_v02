import json
from urllib.parse import urlencode

import frappe
from frappe import _
from frappe.integrations.utils import make_get_request
from frappe.utils import get_datetime, get_time, get_timedelta, getdate

from real_group_hrms.tasks.process_employee_checkin import (
    fetch_shift_details,
    find_closest_shift_from_punch_time,
    get_employee_allowed_shifts,
)


def validate(doc, method=None):
    doc.custom_processed_time = doc.time
    update_processed_time(doc)
    set_geolocation(doc)


def before_insert(doc, method=None):
    assign_closest_shift_on_insert(doc, method)
    # apply_short_leave_attendance_on_late_checkin(doc)


def after_insert(doc, method=None):
    send_sms_on_late_checkin(doc)
    apply_short_leave_attendance_on_late_checkin(doc)


def before_save(doc, method=None):
    validate_remote_checkin(doc)


def update_processed_time(doc):
    if not is_first_checkin(doc) or doc.log_type != "IN":
        return

    employee = frappe.get_cached_doc("Employee", doc.employee, for_update=False)
    data = fetch_shift_details(doc.shift, doc.time, employee.grade)
    shift_start_time = data.get("actual_start")

    start_time = get_datetime(shift_start_time)
    checkin_time = get_datetime(doc.time)

    if checkin_time < start_time:
        doc.custom_processed_time = start_time


def apply_short_leave_attendance_on_late_checkin(doc):
    if not is_first_checkin(doc) or doc.log_type != "IN":
        return
    employee = frappe.get_doc("Employee", doc.employee, for_update=False)
    grade = frappe.get_doc("Employee Grade", employee.grade, for_update=False)

    if (
        grade.custom_short_leave_type != "Personal"
        or not grade.custom_number_of_leaves
        or not grade.custom_hours_per_leave
    ):
        return

    data = fetch_shift_details(doc.shift, doc.time, employee.grade)
    shift_start_time = data.get("start_datetime")

    start_time = get_datetime(shift_start_time)
    checkin_time = get_datetime(doc.time)
    diff = checkin_time - (
        start_time
        + (
            get_timedelta(data.get("shift_type").get("custom_late_entry_grace_period"))
            if data.get("shift_type").get("custom_late_entry_grace_period")
            else get_timedelta()
        )
    )

    if diff > get_timedelta() and get_timedelta() < diff < grade.custom_hours_per_leave:
        try:
            short_leave = frappe.get_doc(
                {
                    "doctype": "Short Leave",
                    "employee": doc.employee,
                    "for_date": getdate(doc.time),
                    "shift": doc.shift,
                    "shift_start_time": start_time,
                    "punch_time": checkin_time,
                }
            )
            short_leave.insert(ignore_permissions=True)
            short_leave.submit()
            short_leave.add_tag("Auto Created on Late Checkin")
            minutes = int(diff.total_seconds() / 60)
            short_leave.add_comment(
                text=f"Created automatically for late check-in: {minutes} minutes late"
            )
        except Exception:
            frappe.log_error(
                frappe.get_traceback(), "Auto Attendance Request Creation Failed"
            )


def send_sms_on_late_checkin(doc):
    if doc.log_type != "IN":
        return

    # Skip backdated checkins recreated during reprocessing/imports.
    if getdate(doc.time) != getdate():
        return

    sms_gateway = get_sms_creds()
    if not sms_gateway:
        return

    url = sms_gateway.get("url")
    api_key = sms_gateway.get("api_key")
    sender_id = sms_gateway.get("sender_id")
    template_id = sms_gateway.get("template_id") or sms_gateway.get("templateid")

    if not url or not api_key or not sender_id or not template_id:
        frappe.log_error(
            "Missing one or more SMS config values: url, api_key, sender_id, template_id",
            "Late Checkin SMS Config Incomplete",
        )
        return

    employee = frappe.get_cached_doc("Employee", doc.employee, for_update=False)
    employee_grade = frappe.get_cached_doc(
        "Employee Grade", employee.grade, for_update=False
    )
    if not employee.cell_number or (
        employee_grade.custom_single_punch_applicable
        or employee_grade.custom_no_punch_applicable
    ):
        return

    if not is_first_checkin(doc):
        return

    shift_start_time = doc.shift_start

    if not shift_start_time:
        data = fetch_shift_details(doc.shift, doc.time, employee.grade)
        shift_start_time = data.get("start_datetime")

    if not shift_start_time:
        return
    shift_start_time = get_datetime(shift_start_time)
    checkin_time = get_datetime(doc.time)

    if shift_start_time > checkin_time:
        return

    late_seconds = max(0, int((checkin_time - shift_start_time).total_seconds()))
    difference_in_minutes = late_seconds // 60

    # Keep the SMS body aligned with the approved DLT template format.
    message = (
        f"Hello {doc.employee_name},\n\n"
        f"You have arrived {difference_in_minutes} minutes late at work today and "
        f"your clock-in time is {doc.time} hours.\n\n"
        f"Regards,\n"
        f"REAL Group"
    )

    query_params = {
        "apikey": api_key,
        "senderid": sender_id,
        "number": employee.cell_number,
        "message": message,
        "templateid": template_id,
    }
    url = f"{url}?{urlencode(query_params)}"
    try:
        sms_response = make_get_request(url)
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            f"Late Checkin SMS Failed for Employee Checkin {doc.name}",
        )
        return

    try:
        sms_response_log = frappe.get_doc(
            {
                "doctype": "SMS Response Log",
                "response": json.dumps(sms_response),
                "checkin": doc.name,
            }
        )
        sms_response_log.insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            f"Late Checkin SMS Response Log Failed for Employee Checkin {doc.name}",
        )


def is_first_checkin(doc):
    for_date = getdate(doc.time)
    return (
        frappe.db.count(
            "Employee Checkin",
            {
                "employee": doc.employee,
                "log_type": "IN",
                "time": ["Between", [for_date, for_date]],
            },
        )
        < 2
    )


def get_sms_creds():
    setup = frappe.local.conf.get("sms_integration", {})
    if not setup:
        return None
    return setup


def set_geolocation(doc):
    from real_group_hrms.utils import set_geolocation_from_coordinates

    set_geolocation_from_coordinates(doc)


def validate_remote_checkin(doc):
    if not doc.employee:
        return
    posting_location = frappe.db.get_value(
        "Employee", doc.employee, "custom_is_remote_office"
    )
    if posting_location:
        if not (doc.custom_latitude and doc.custom_longitude):
            frappe.throw(
                _(
                    "For employees with 'Remote Office' posting location, latitude and longitude are mandatory."
                )
            )


def assign_closest_shift_on_insert(doc, method=None):
    if not doc.shift and doc.employee and doc.time:
        punch_time_str = get_time(doc.time)
        punch_date_str = getdate(doc.time)
        employee = frappe.get_cached_doc("Employee", doc.employee, for_update=False)
        doc_time_dt = get_datetime(doc.time)
        try:
            allowed_shifts = get_employee_allowed_shifts(doc.employee, punch_date_str)
            if allowed_shifts:
                closest_shift_name = find_closest_shift_from_punch_time(
                    allowed_shifts, punch_time_str
                )
                if closest_shift_name:
                    doc.shift = closest_shift_name
                    shift_info = fetch_shift_details(
                        shift_type=doc.shift,
                        for_timestamp=doc_time_dt,
                        grade=employee.grade,
                    )
                    doc.shift_start = shift_info.start_datetime
                    doc.shift_end = shift_info.end_datetime
                    doc.shift_actual_start = shift_info.actual_start
                    doc.shift_actual_end = shift_info.actual_end
        except Exception as e:
            frappe.log_error(
                frappe.get_traceback(),
                f"Failed to auto-assign shift for {doc.employee} on {punch_date_str}: {e}",
            )
