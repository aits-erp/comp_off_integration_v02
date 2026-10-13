import frappe
from frappe import _
from hrms.hr.doctype.employee_checkin.employee_checkin import (
    EmployeeCheckin,
    handle_attendance_exception,
    skip_attendance_in_checkins,
    update_attendance_in_checkins,
)
from real_group_hrms.utils import set_geolocation_from_coordinates


class EmployeeCheckinOverride(EmployeeCheckin):
    @frappe.whitelist()
    def set_geolocation(self):
        set_geolocation_from_coordinates(self)

    def fetch_shift(self):
        if hasattr(self, "flags") and not getattr(self.flags, "is_shift_fetch_required", False):
            return
        super().fetch_shift()

# Taken from latest frappe hrms codebase, which includes half-day attendance handling
def mark_attendance_and_link_log(
    logs,
    attendance_status,
    attendance_date,
    working_hours=None,
    late_entry=False,
    early_exit=False,
    in_time=None,
    out_time=None,
    shift=None,
):
    """Creates an attendance and links the attendance to the Employee Checkin.
    Note: If attendance is already present for the given date, the logs are marked as skipped and no exception is thrown.

    :param logs: The List of 'Employee Checkin'.
    :param attendance_status: Attendance status to be marked. One of: (Present, Absent, Half Day, Skip). Note: 'On Leave' is not supported by this function.
    :param attendance_date: Date of the attendance to be created.
    :param working_hours: (optional)Number of working hours for the given date.
    """
    log_names = [x.name for x in logs]
    employee = logs[0].employee

    if attendance_status == "Skip":
        skip_attendance_in_checkins(log_names)
        return None

    elif attendance_status in ("Present", "Absent", "Half Day"):
        try:
            frappe.db.savepoint("attendance_creation")
            if attendance := get_existing_half_day_attendance(employee, attendance_date):
                frappe.db.set_value(
                    "Attendance",
                    attendance.name,
                    {
                        "working_hours": working_hours,
                        "shift": shift,
                        "late_entry": late_entry,
                        "early_exit": early_exit,
                        "in_time": in_time,
                        "out_time": out_time,
                        "half_day_status": "Absent" if attendance_status == "Absent" else "Present",
                        "modify_half_day_status": 0,
                    },
                )
            else:
                attendance = frappe.new_doc("Attendance")
                attendance.update(
                    {
                        "doctype": "Attendance",
                        "employee": employee,
                        "attendance_date": attendance_date,
                        "status": attendance_status,
                        "working_hours": working_hours,
                        "shift": shift,
                        "late_entry": late_entry,
                        "early_exit": early_exit,
                        "in_time": in_time,
                        "out_time": out_time,
                        "half_day_status": "Absent" if attendance_status == "Half Day" else None,
                    }
                ).submit()

            if attendance_status == "Absent":
                attendance.add_comment(
                    text=_("Employee was marked Absent for not meeting the working hours threshold.")
                )

            update_attendance_in_checkins(log_names, attendance.name)
            return attendance

        except frappe.ValidationError as e:
            handle_attendance_exception(log_names, e)

    else:
        frappe.throw(_("{} is an invalid Attendance Status.").format(attendance_status))


def get_existing_half_day_attendance(employee, attendance_date):
    attendance_name = frappe.db.exists(
        "Attendance",
        {
            "employee": employee,
            "attendance_date": attendance_date,
            "status": "Half Day",
            "modify_half_day_status": 1,
            "leave_type": ("is", "set"),
        },
    )

    if attendance_name:
        attendance_doc = frappe.get_doc("Attendance", attendance_name)
        return attendance_doc
    return None
