import frappe
from frappe.utils import getdate


def pull():
    start_date = getdate("2025-05-31")
    end_date = getdate("2025-08-31")

    data = frappe.db.sql(
        "SELECT * FROM `tabbioattendancelog` WHERE `punch_date` BETWEEN %s AND %s", (start_date, end_date), as_dict=1
    )
    for d in data:
        try:
            frappe.get_doc(
                {
                    "doctype": "bioattendancelog",
                    "employee_id": d.employee_id,
                    "punch_date": d.punch_date,
                    "punch_time": d.punch_time,
                    "punch_direction": d.punch_direction,
                    "device_id": d.device_id,
                    "terminal_id": d.terminal_id,
                    "time_pro_reference_id": d.time_pro_reference_id,
                    "punch_date_backup": d.punch_date_backup,
                    "present_day": d.present_day,
                    "area": d.area,
                }
            ).insert(ignore_permissions=True)
            frappe.db.commit()
        except Exception:
            continue
