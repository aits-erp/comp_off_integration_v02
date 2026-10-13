import frappe
from frappe.utils import add_days, getdate

from real_group_hrms.utils import is_holiday_for_employee


def process():
    grade_list = frappe.get_all(
        "Employee Grade", pluck="name", filters={"custom_no_punch_applicable": 1, "custom_single_punch_applicable": 0}
    )
    if not grade_list:
        return

    employees = frappe.get_all(
        "Employee",
        fields=["name", "holiday_list", "company"],
        filters={"grade": ["in", grade_list], "status": "Active"},
    )
    if not employees:
        return

    for emp in employees:
        try:
            has_attendance = frappe.db.exists(
                "Attendance",
                {"employee": emp.name, "attendance_date": add_days(getdate(), -1), "docstatus": 1},
            )
            if has_attendance:
                continue

            holiday = is_holiday_for_employee(emp.name, add_days(getdate(), -1))

            if holiday:
                attendance = frappe.get_doc(
                    {
                        "doctype": "Attendance",
                        "employee": emp.name,
                        "attendance_date": add_days(getdate(), -1),
                        "status": "Present",
                        "company": emp.company,
                        "custom_attendance_tag": "HO" if not holiday.get("is_weekly_off") else "WO",
                    }
                )
            else:
                attendance = frappe.get_doc(
                    {
                        "doctype": "Attendance",
                        "employee": emp.name,
                        "attendance_date": add_days(getdate(), -1),
                        "status": "Present",
                        "company": emp.company,
                        "custom_attendance_tag": "P",
                    }
                )
            attendance.insert(ignore_permissions=True)
            attendance.submit()
            attendance.add_tag("No Check in Required")
            frappe.db.commit()  # Commit after each successful attendance creation, so that in case of failure, previous records are saved.
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Error in processing attendance for {emp.name}")
            continue
