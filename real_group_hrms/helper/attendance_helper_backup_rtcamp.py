from datetime import date, timedelta

import frappe
from frappe.utils import (
    add_days,
    cint,
    format_time,
    get_first_day,
    get_last_day,
    get_time,
    get_timedelta,
    getdate,
)
from hrms.hr.doctype.employee_checkin.employee_checkin import (
    calculate_working_hours,
    mark_attendance_and_link_log,
    update_attendance_in_checkins,
)

from real_group_hrms.utils import (
    convert_time_to_hours,
    convert_time_to_minutes,
    get_holiday_dates_for_employee,
    is_holiday_for_employee,
)


# Main function to create or update attendance
def create_attendance(employee: str, date: str | date, logs: list[dict] | None, reprocess_ref=None) -> None:
    employee_doc = frappe.get_cached_doc("Employee", employee)
    if logs:
        logs = update_time(logs)

    if isinstance(date, str):
        date = getdate(date)
    existing_attendance = has_attendance(employee, date)

    holiday = is_holiday_for_employee(employee, date)
    emp_grade = frappe.get_value("Employee", employee, "grade")
    allowed_late_day, deduction_cycle = frappe.db.get_value(
        "Employee Grade",
        emp_grade,
        ["custom_allowed_late_count_days", "custom_late_entry_deduction_cycle"],
    )

    if existing_attendance:
        existing_attendance = frappe.get_doc("Attendance", existing_attendance)

        # Important for reprocess: attendance for a date may be created earlier in the same
        # job as Absent (no logs found yet) and later the correct logs arrive (e.g. night shift).
        # In that case we must update the existing submitted Attendance rather than skipping.
        if logs:
            shift = logs[0].shift if logs else existing_attendance.shift
            (
                attendance_status,
                working_hours,
                late_entry,
                early_exit,
                in_time,
                out_time,
            ) = get_attendance(logs, employee_doc.grade, shift)

            # If the Attendance was first created as Absent (no logs yet) and logs arrive later
            # (night shift / delayed sync), update the actual status and timings.
            if existing_attendance.status == "Absent":
                existing_attendance.db_set(
                    {
                        "status": attendance_status,
                        "working_hours": working_hours,
                        "shift": shift,
                        "late_entry": late_entry,
                        "early_exit": early_exit,
                        "in_time": in_time,
                        "out_time": out_time,
                        "custom_reprocess_reference": reprocess_ref,
                    }
                )

            # If there's already a half-day leave linked, keep it as half-day unless logs
            # justify marking it present.
            elif existing_attendance.status == "Half Day" and existing_attendance.leave_application:
                if attendance_status == "Half Day":
                    attendance_status = "Present"
                if attendance_status == "Absent":
                    attendance_status = "Half Day"

                existing_attendance.db_set(
                    {
                        "status": attendance_status,
                        "working_hours": working_hours + existing_attendance.working_hours
                        if existing_attendance.working_hours
                        else working_hours,
                        "shift": shift,
                        "late_entry": late_entry,
                        "early_exit": early_exit,
                        "in_time": in_time,
                        "out_time": out_time,
                        "custom_reprocess_reference": reprocess_ref,
                    }
                )
            else:
                existing_attendance.db_set(
                    {
                        "working_hours": working_hours + existing_attendance.working_hours
                        if existing_attendance.working_hours
                        else working_hours,
                        "shift": shift if not existing_attendance.shift else existing_attendance.shift,
                        "custom_reprocess_reference": reprocess_ref,
                    }
                )
            update_attendance_in_checkins([c.name for c in logs], existing_attendance.name)
            # Keep tags consistent when we change status on an already-submitted doc.
            try:
                from real_group_hrms.doc_events.attendance import allocate_c_off, allocate_incentive, update_attendance_tag

                update_attendance_tag(existing_attendance)
                if not reprocess_ref:
                    allocate_incentive(existing_attendance)
                    allocate_c_off(existing_attendance)
            except Exception:
                frappe.log_error(
                    frappe.get_traceback(),
                    f"[Attendance] Failed to update tag for {existing_attendance.name}",
                )
    elif holiday and not logs:
        if holiday.get("is_half_day"):
            frappe.get_doc(
                {
                    "doctype": "Attendance",
                    "attendance_date": date,
                    "status": "Half Day",
                    "employee": employee,
                    "custom_attendance_tag": "HO" if not holiday.get("is_weekly_off") else "WO",
                    "custom_reprocess_reference": reprocess_ref,
                },
            ).insert(ignore_permissions=True).submit()
        else:
            frappe.get_doc(
                {
                    "doctype": "Attendance",
                    "attendance_date": date,
                    "status": "Present",
                    "employee": employee,
                    "custom_attendance_tag": "HO" if not holiday.get("is_weekly_off") else "WO",
                    "custom_reprocess_reference": reprocess_ref,
                },
            ).insert(ignore_permissions=True).submit()
    elif logs and not holiday:
        shift = logs[0].shift if logs else existing_attendance.shift

        (
            attendance_status,
            working_hours,
            late_entry,
            early_exit,
            in_time,
            out_time,
        ) = get_attendance(logs, employee_doc.grade, shift)
        attendance = mark_attendance_and_link_log(
            logs,
            attendance_status,
            date,
            working_hours,
            late_entry,
            early_exit,
            in_time,
            out_time,
            shift,
        )
        attendance.db_set("custom_reprocess_reference", reprocess_ref)
        mark_half_day_based_on_deduction_cycle(employee, allowed_late_day, deduction_cycle, attendance)
    elif logs and holiday:
        is_half_day_holiday = holiday.get("is_half_day")
        if is_half_day_holiday:
            doc = frappe.get_doc(
                {
                    "doctype": "Attendance",
                    "employee": employee,
                    "attendance_date": date,
                    "status": "Half Day",
                    "custom_attendance_tag": "HO" if not holiday.get("is_weekly_off") else "WO",
                    "custom_reprocess_reference": reprocess_ref,
                }
            ).insert(ignore_permissions=True)
        else:
            doc = frappe.get_doc(
                {
                    "doctype": "Attendance",
                    "employee": employee,
                    "attendance_date": date,
                    "status": "Present",
                    "custom_attendance_tag": "HO" if not holiday.get("is_weekly_off") else "WO",
                    "custom_reprocess_reference": reprocess_ref,
                }
            ).insert(ignore_permissions=True)
        shift = logs[0].shift if logs else existing_attendance.shift

        (
            attendance_status,
            working_hours,
            late_entry,
            early_exit,
            in_time,
            out_time,
        ) = get_attendance(logs, employee_doc.grade, shift)

        if attendance_status == "Half Day" and is_half_day_holiday:
            attendance_status = "Present"
        doc.update(
            {
                "status": attendance_status,
                "working_hours": working_hours,
                "shift": shift,
                "late_entry": late_entry,
                "early_exit": early_exit,
                "in_time": in_time,
                "out_time": out_time,
                "custom_reprocess_reference": reprocess_ref,
            }
        )
        doc.save(ignore_permissions=True).submit()
        update_attendance_in_checkins([c.name for c in logs], doc.name)

    else:
        # Employee has no night shift logs and it's not a holiday - mark as absent

        attendance = frappe.get_doc(
            {
                "doctype": "Attendance",
                "employee": employee,
                "attendance_date": date,
                "status": "Absent",
                "custom_attendance_tag": "A",
                "custom_reprocess_reference": reprocess_ref,
            }
        ).insert(ignore_permissions=True)
        attendance.submit()


def update_time(checkins: list):
    checkins = sorted(checkins, key=lambda x: x["time"])
    for checkin in checkins:
        checkin._backup_time = checkin.time
        checkin.time = checkin.custom_processed_time

    return checkins


def has_attendance(employee, attendance_date):
    return frappe.db.exists(
        "Attendance",
        {"employee": employee, "attendance_date": attendance_date, "docstatus": ["<", 2]},
    )


def get_attendance(logs, grade, shift_type):
    if len(logs) < 2:
        return "Absent", 0, False, False, None, None

    late_entry = early_exit = False
    total_working_hours, in_time, out_time = calculate_working_hours(
        logs, "Strictly based on Log Type in Employee Checkin", "Every Valid Check-in and Check-out"
    )
    grade = frappe.get_cached_doc("Employee Grade", grade)
    shift = frappe.get_cached_doc("Shift Type", shift_type)
    force_half_day_due_to_late = False
    if cint(shift.enable_late_entry_marking) and in_time:
        shift_grace_minutes = convert_time_to_minutes(shift.custom_late_entry_grace_period)
        grade_grace_minutes = convert_time_to_minutes(grade.custom_late_entry_grace_period)
        grade_grace_minutes = max(grade_grace_minutes, shift_grace_minutes)

        shift_grace_time = logs[0].shift_start + timedelta(minutes=shift_grace_minutes)
        grade_grace_time = logs[0].shift_start + timedelta(minutes=grade_grace_minutes)

        if in_time <= shift_grace_time:
            late_entry = False
        elif in_time <= grade_grace_time:
            late_entry = True
        else:
            late_entry = False
            force_half_day_due_to_late = True

    if (
        cint(shift.enable_early_exit_marking)
        and out_time
        and out_time
        < logs[0].shift_end - timedelta(minutes=cint(convert_time_to_minutes(shift.custom_early_exit_grace_period)))
    ):
        early_exit = True

    short_leaves = get_short_leaves(logs[0].employee, getdate(logs[0].shift_start))
    if short_leaves:
        for req in short_leaves:
            start = get_timedelta(format_time(get_time(req.shift_start_time)))
            end = get_timedelta(format_time(get_time(req.punch_time)))
            hours = convert_time_to_hours(abs(end - start))
            total_working_hours += hours

    working_threshold = convert_time_to_hours(shift.custom_working_hours_threshold_for_present)
    half_day_threshold = convert_time_to_hours(shift.custom_working_hours_threshold_for_half_day)
    absent_threshold = convert_time_to_hours(shift.custom_working_hours_threshold_for_absent)

    if working_threshold and total_working_hours >= working_threshold:
        status = "Present"
    elif half_day_threshold and total_working_hours >= half_day_threshold and total_working_hours < working_threshold:
        status = "Half Day"
    elif absent_threshold and total_working_hours < absent_threshold:
        status = "Absent"
    else:
        status = "Absent"

    if force_half_day_due_to_late and status == "Present":
        status = "Half Day"

    if (
        late_entry
        and working_threshold
        and half_day_threshold
        and total_working_hours < working_threshold
        and total_working_hours >= half_day_threshold
    ):
        late_entry = False
        status = "Half Day"

    return status, total_working_hours, late_entry, early_exit, in_time, out_time


def get_short_leaves(employee, date):
    data = frappe.get_all(
        "Short Leave",
        filters={"employee": employee, "for_date": date, "docstatus": 1},
        fields=["shift_start_time", "punch_time"],
    )
    return data


def mark_half_day_based_on_deduction_cycle(employee, allowed_late_day, deduction_cycle, attendance):
    if not allowed_late_day or not deduction_cycle:
        return
    if not attendance or not attendance.late_entry or attendance.status != "Present":
        return
    month_start = get_first_day(attendance.attendance_date)
    month_end = get_last_day(attendance.attendance_date)
    holiday_dates = get_holiday_dates_for_employee(employee, month_start, month_end)

    _filter_dates = []
    while month_start <= month_end:
        if month_start not in holiday_dates:
            _filter_dates.append(month_start)
        month_start = add_days(month_start, 1)

    monthly_late_count = frappe.db.count(
        "Attendance",
        {
            "employee": employee,
            "attendance_date": ["in", _filter_dates],
            "docstatus": 1,
            "status": ["in", ["Present", "Half Day"]],
            "late_entry": 1,
        },
    )
    if monthly_late_count > allowed_late_day:
        if monthly_late_count % deduction_cycle == 0 and attendance:
            frappe.db.set_value("Attendance", attendance.name, "status", "Half Day")
            frappe.db.set_value("Attendance", attendance.name, "custom_attendance_tag", "HD")