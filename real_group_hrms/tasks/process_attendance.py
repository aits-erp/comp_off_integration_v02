from datetime import datetime, time
from itertools import groupby

import frappe
from frappe.utils import (
    add_days,
    get_datetime,
    getdate,
)

from real_group_hrms.helper.attendance_helper import create_attendance


def process(from_date=None, employee_names: list | None = None, reprocess_ref=None):
    start_date = add_days(getdate(from_date), -1)
    end_date = getdate(from_date)
    start_date_for_night_shift = add_days(getdate(from_date), -2)
    end_date_for_night_shift = add_days(getdate(from_date), -1)

    if not employee_names:
        grades = frappe.get_all(
            "Employee Grade",
            filters={"custom_single_punch_applicable": 0, "custom_no_punch_applicable": 0},
            pluck="name",
        )
        employees = frappe.get_all(
            "Employee",
            filters={"grade": ["in", grades], "status": "Active", "date_of_joining": ["<", start_date_for_night_shift]},
            pluck="name",
        )
    else:
        employees = employee_names

    day_shift_checkins = frappe.get_all(
        "Employee Checkin",
        filters={
            "employee": ["in", employees],
            "shift_start": [">=", get_datetime(start_date)],
            "shift_end": ["<=", get_datetime(end_date)],
            "attendance": ["is", "not set"],
        },
        order_by="time",
        fields=["*"],
    )

    logs = sorted(day_shift_checkins, key=lambda x: (x["employee"], x["time"]))

    # Group logs by employee
    logs_by_employee = {}
    for employee, group in groupby(logs, key=lambda x: x["employee"]):
        logs_by_employee[employee] = list(group)

    # Process all employees, including those without logs
    for employee in employees:
        group = logs_by_employee.get(employee, [])
        create_attendance_if_salary_not_processed(employee, start_date, group, reprocess_ref)

    # Processing Night Shift Employees
    night_shift_checkins = frappe.get_all(
        "Employee Checkin",
        filters={
            "employee": ["in", employees],
            "shift_start": [">=", get_datetime(start_date_for_night_shift)],
            "shift_end": ["<=", datetime.combine(end_date_for_night_shift, time(23, 59, 59))],
            "attendance": ["is", "not set"],
        },
        order_by="time",
        fields=["*"],
    )
    night_logs = sorted(night_shift_checkins, key=lambda x: (x["employee"], x["time"]))

    # Group night logs by employee
    night_logs_by_employee = {}
    for employee, group in groupby(night_logs, key=lambda x: x["employee"]):
        night_logs_by_employee[employee] = list(group)

    # Process all employees for night shift, including those without logs
    for employee in employees:
        group = night_logs_by_employee.get(employee, [])
        create_attendance_if_salary_not_processed(
            employee, start_date_for_night_shift, group, reprocess_ref
        )


def create_attendance_if_salary_not_processed(employee, attendance_date, logs, reprocess_ref=None):
    salary_slip = get_salary_slip_for_attendance(employee, attendance_date)
    if salary_slip:
        log_salary_slip_skip(employee, attendance_date, salary_slip)
        return

    try:
        create_attendance(employee, attendance_date, logs, reprocess_ref)
    except frappe.ValidationError:
        # A Salary Slip can be created after the initial check. Skip only this
        # known payroll lock; let every other validation failure fail normally.
        salary_slip = get_salary_slip_for_attendance(employee, attendance_date)
        if not salary_slip:
            raise

        log_salary_slip_skip(employee, attendance_date, salary_slip)


def get_salary_slip_for_attendance(employee, attendance_date):
    return frappe.db.get_value(
        "Salary Slip",
        {
            "employee": employee,
            "start_date": ["<=", attendance_date],
            "end_date": [">=", attendance_date],
            "docstatus": ["!=", 2],
        },
        ["name", "docstatus"],
        as_dict=True,
    )


def log_salary_slip_skip(employee, attendance_date, salary_slip):
    status = "Submitted" if salary_slip.docstatus == 1 else "Draft"
    frappe.log_error(
        title="Attendance skipped: Salary Slip exists",
        message=(
            f"Skipped automatic attendance for employee {employee} on {attendance_date}. "
            f"Salary Slip {salary_slip.name} is {status}."
        ),
    )
