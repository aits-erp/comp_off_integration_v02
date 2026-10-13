import frappe
from frappe.utils import add_days, get_datetime, getdate, today

from real_group_hrms.utils import is_holiday_for_employee


def process():
    grade_list = frappe.get_all(
        "Employee Grade", pluck="name", filters={"custom_no_punch_applicable": 0, "custom_single_punch_applicable": 1}
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

    start_time = get_datetime(add_days(today(), -1))
    end_time = get_datetime(today())

    for emp in employees:
        try:
            has_attendance = frappe.db.exists(
                "Attendance",
                {"employee": emp.name, "attendance_date": add_days(today(), -1), "docstatus": 1},
            )
            if has_attendance:
                continue
            holiday = is_holiday_for_employee(emp.name, add_days(today(), -1))
            filters = [["employee", "=", emp.name], ["time", ">=", start_time], ["time", "<", end_time]]
            checkins = frappe.get_all(
                "Employee Checkin", filters=filters, fields=["name", "shift_start", "log_type"], order_by="shift_start asc"
            )
            emp_checkin = len(checkins)
            has_valid_in_out = any(c.get("log_type") == "IN" for c in checkins) and any(
                c.get("log_type") == "OUT" for c in checkins
            )
            if holiday and has_valid_in_out:
                attendance = frappe.get_doc(
                    {
                        "doctype": "Attendance",
                        "employee": emp.name,
                        "attendance_date": add_days(today(), -1),
                        "status": "Present",
                        "company": emp.company,
                        "custom_attendance_tag": "POW" if holiday.get("is_weekly_off") else "POH",
                    }
                )
                attendance.insert(ignore_permissions=True)
                attendance.submit()
            elif holiday:
                attendance = frappe.get_doc(
                    {
                        "doctype": "Attendance",
                        "employee": emp.name,
                        "attendance_date": add_days(today(), -1),
                        "status": "Present",
                        "company": emp.company,
                        "custom_attendance_tag": "HO" if not holiday.get("is_weekly_off") else "WO",
                    }
                )
                attendance.insert(ignore_permissions=True)
                attendance.submit()
            else:
                if not emp_checkin or emp_checkin == 0:
                    attendance = frappe.get_doc(
                        {
                            "doctype": "Attendance",
                            "employee": emp.name,
                            "attendance_date": add_days(today(), -1),
                            "status": "Absent",
                            "company": emp.company,
                            "custom_attendance_tag": "A",
                        }
                    )
                    attendance.insert(ignore_permissions=True)
                    attendance.submit()

                else:
                    shift_date = getdate(checkins[0].get("shift_start")) if checkins[0].get("shift_start") else add_days(today(), -1)
                    attendance = frappe.get_doc(
                        {
                            "doctype": "Attendance",
                            "employee": emp.name,
                            "attendance_date": shift_date,
                            "status": "Present",
                            "company": emp.company,
                            "custom_attendance_tag": "P",
                        }
                    )
                    attendance.insert(ignore_permissions=True)
                    attendance.submit()
                    for checkin in checkins:
                        frappe.db.set_value("Employee Checkin", checkin.get("name"), "attendance", attendance.name)
            attendance.add_tag("Single Check in Required")
            frappe.db.commit()  # Commit after each successful attendance creation, so that in case of failure, previous records are saved.
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Error in processing attendance for {emp.name}")
            continue
