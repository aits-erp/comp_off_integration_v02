import frappe

from real_group_hrms.overrides.attendance_request import (
    calculate_request_working_hours_for_date,
    get_working_hours_timedelta,
)


def execute():
    updated_records = 0
    records = frappe.db.sql(
        """
        SELECT
            att.name,
            att.attendance_request,
            att.attendance_date,
            ar.custom_from_time,
            ar.custom_to_time,
            COALESCE(ar.shift, att.shift) AS shift_name
        FROM `tabAttendance` att
        INNER JOIN `tabAttendance Request` ar
            ON ar.name = att.attendance_request
        WHERE
            att.docstatus != 2
            AND att.attendance_request IS NOT NULL
            AND att.working_hours < 0
            AND ar.custom_from_time IS NOT NULL
            AND ar.custom_to_time IS NOT NULL
        """,
        as_dict=True,
    )

    for record in records:
        try:
            working_hours = calculate_request_working_hours_for_date(
                record.attendance_date,
                record.custom_from_time,
                record.custom_to_time,
                record.shift_name,
            )
            if working_hours <= 0:
                continue

            frappe.db.set_value(
                "Attendance",
                record.name,
                {
                    "working_hours": working_hours,
                    "custom_working_hours": get_working_hours_timedelta(working_hours),
                },
                update_modified=False,
            )
            updated_records += 1
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                f"[Patch] Failed to fix cross-day attendance request hours for {record.name}",
            )

    if updated_records:
        frappe.db.commit()
