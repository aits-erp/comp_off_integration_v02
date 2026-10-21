# KEEP IT FOR REFERENCE
from datetime import timedelta

import frappe
from frappe.utils import add_days, get_date_str, get_timedelta, getdate


def process():
    grades = get_grades()
    if not grades:
        return

    grade_names = [grade.name for grade in grades]
    employees = get_employees(grade_names)
    if not employees:
        return

    start_date = add_days(getdate(), -1)
    end_date = getdate()

    attendances = frappe.get_all(
        "Attendance",
        fields=["*"],
        filters={
            "employee": ("in", [e.name for e in employees]),
            "attendance_date": ["between", [start_date, end_date]],
            "status": ["not in", ["On Leave", "Absent"]],
            "docstatus": 1,
        },
    )
    employee_attendance = {}
    for attendance in attendances:
        if attendance.employee not in employee_attendance:
            employee_attendance[attendance.employee] = []
        employee_attendance[attendance.employee].append(attendance)

    for employee, attendances in employee_attendance.items():
        if not attendances:
            continue
        employee_doc = frappe.get_cached_doc("Employee", employee)
        grade = employee_doc.grade
        grade = next((g for g in grades if g.name == grade), None)
        if not grade:
            continue

        validity = grade.custom_comp_off_validity
        worked_on_date_map = {}
        for attendance in attendances:
            att_date = attendance.get("attendance_date")
            if att_date not in worked_on_date_map:
                worked_on_date_map[att_date] = {"total_hours": 0, "shift": attendance.get("shift")}
            worked_on_date_map[att_date]["total_hours"] += attendance.get("working_hours", 0)

        for att_date, details in worked_on_date_map.items():
            status = ""
            holiday = frappe.db.exists(
                "Holiday",
                {
                    "holiday_date": att_date,
                    "parent": employee_doc.holiday_list,
                    "parenttype": "Holiday List",
                    "parentfield": "holidays",
                },
                cache=True,
            )
            if holiday:
                holiday = frappe.get_cached_doc("Holiday", holiday, for_update=False)
                if holiday.weekly_off:
                    status = "POW"
                else:
                    status = "POH"

            shift = details.get("shift")
            shift = frappe.get_cached_doc("Shift Type", shift) if shift else None
            if not shift:
                continue

            shift_duration = abs(get_timedelta(shift.start_time) - get_timedelta(shift.end_time)).total_seconds() / 3600

            c_matrix = frappe.db.exists(
                "Compensation Matrix", {"shift_duration": timedelta(hours=shift_duration)}, cache=True
            )
            if not c_matrix:
                continue
            c_matrix = frappe.get_cached_doc("Compensation Matrix", c_matrix)

            if details.get("total_hours", 0) <= shift_duration:
                continue

            if holiday and grade.custom_present_on_holiday == "Comp Off":
                diff = details.get("total_hours", 0)
            else:
                diff = details.get("total_hours", 0) - shift_duration
                status = "EW"

            worked_hrs_in_delta = timedelta(hours=diff)

            matched_c_matrix = next((m for m in c_matrix.items if m.from_hrs < worked_hrs_in_delta <= m.to_hrs), None)
            if not matched_c_matrix:
                continue

            credit = matched_c_matrix.c_off_credit
            if not credit:
                continue

            savepoint_name = f"{employee}_{get_date_str(att_date)}".replace("-", "_")

            frappe.db.savepoint(savepoint_name)

            try:
                comp_off = frappe.get_doc(
                    {
                        "doctype": "Compensatory Leave Request",
                        "employee": employee,
                        "work_from_date": getdate(att_date),
                        "work_end_date": getdate(att_date),
                        "credit": credit,
                        "leave_type": "Compensatory Off",
                        "status": f"{status}:{diff}",
                        "expiry": add_days(getdate(att_date), validity),
                        "reason": status,
                    }
                )
                comp_off.insert(ignore_permissions=True)
                comp_off.submit()
            except Exception:
                frappe.db.rollback(save_point=savepoint_name)
                frappe.log_error(frappe.get_traceback(), "Comp-Off Allocation Failed")


def get_grades():
    return frappe.get_all(
        "Employee Grade",
        fields=["*"],
        or_filters={"custom_present_on_holiday": "Comp Off", "custom_extra_work_hour": "Comp Off"},
    )


def get_employees(grades: list[str]):
    return frappe.get_all(
        "Employee",
        fields=["*"],
        filters={"status": "Active", "grade": ("in", grades)},
    )
