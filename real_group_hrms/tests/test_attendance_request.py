from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, get_year_ending, get_year_start, getdate

from erpnext.setup.doctype.employee.test_employee import make_employee

from hrms.hr.doctype.shift_type.test_shift_type import setup_shift_type
from hrms.payroll.doctype.salary_slip.test_salary_slip import make_holiday_list

from real_group_hrms.patches.fix_cross_day_attendance_request_hours import (
    execute as fix_cross_day_attendance_request_hours,
)
from real_group_hrms.api.attendance_request import closest_shift_for_time


test_dependencies = ["Employee"]


class TestAttendanceRequestOverride(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee_name = make_employee(
            "test_cross_day_attendance_request@example.com", company="_Test Company"
        )
        cls.employee = frappe.get_doc("Employee", cls.employee_name)

    def setUp(self):
        frappe.db.delete("Attendance", {"employee": self.employee_name})
        frappe.db.delete("Attendance Request", {"employee": self.employee_name})
        frappe.db.delete("Leave Application", {"employee": self.employee_name})

        self.holiday_list_name = "RG Attendance Request Test Holiday List"
        if frappe.db.exists("Holiday List", self.holiday_list_name):
            frappe.delete_doc("Holiday List", self.holiday_list_name, force=1)

        self.holiday_list = make_holiday_list(
            list_name=self.holiday_list_name,
            from_date=get_year_start(getdate()),
            to_date=get_year_ending(getdate()),
            add_weekly_offs=False,
        )
        frappe.db.set_value(
            "Employee", self.employee_name, "holiday_list", self.holiday_list
        )

        self.cross_day_shift = self.make_shift(
            shift_name="RG Test Night Shift",
            start_time="22:00:00",
            end_time="06:00:00",
            custom_is_cross_day=1,
        )
        self.day_shift = self.make_shift(
            shift_name="RG Test Day Shift",
            start_time="09:00:00",
            end_time="18:00:00",
            custom_is_cross_day=0,
        )
        self.early_day_shift = self.make_shift(
            shift_name="RG Test Early Day Shift",
            start_time="06:00:00",
            end_time="14:00:00",
            custom_is_cross_day=0,
        )

    def make_shift(self, shift_name: str, **kwargs):
        if frappe.db.exists("Shift Type", shift_name):
            frappe.delete_doc("Shift Type", shift_name, force=1)
        return setup_shift_type(shift_type=shift_name, **kwargs)

    def make_attendance_request(self, **overrides):
        attendance_request = frappe.get_doc(
            {
                "doctype": "Attendance Request",
                "employee": self.employee_name,
                "from_date": getdate(),
                "to_date": getdate(),
                "reason": "On Duty",
                "company": "_Test Company",
                "shift": self.cross_day_shift.name,
                "custom_from_time": "22:00:00",
                "custom_to_time": "06:00:00",
            }
        )
        attendance_request.update(overrides)
        return attendance_request.submit()

    def make_half_day_leave_application(self, **overrides):
        leave_application = frappe.get_doc(
            {
                "doctype": "Leave Application",
                "employee": self.employee_name,
                "leave_type": "Leave Without Pay",
                "from_date": getdate(),
                "to_date": getdate(),
                "half_day": 1,
                "half_day_date": getdate(),
                "custom_half_type": "Second Half",
                "company": "_Test Company",
                "status": "Approved",
                "leave_approver": "test@example.com",
            }
        )
        leave_application.update(overrides)
        leave_application.insert()
        leave_application.submit()
        return leave_application

    def make_attendance(self, **overrides):
        attendance = frappe.get_doc(
            {
                "doctype": "Attendance",
                "employee": self.employee_name,
                "attendance_date": getdate(),
                "status": "Half Day",
                "company": "_Test Company",
                "shift": self.day_shift.name,
                "working_hours": 7.0,
            }
        )
        attendance.update(overrides)
        attendance.insert(ignore_permissions=True)
        attendance.submit()
        return attendance

    def get_request_attendance(self, attendance_request):
        attendance_name = frappe.db.get_value(
            "Attendance",
            {"attendance_request": attendance_request.name, "docstatus": 1},
            "name",
        )
        return frappe.get_doc("Attendance", attendance_name)

    def get_request_attendances(self, attendance_request):
        attendance_names = frappe.get_all(
            "Attendance",
            filters={"attendance_request": attendance_request.name, "docstatus": 1},
            pluck="name",
            order_by="attendance_date asc",
        )
        return [frappe.get_doc("Attendance", attendance_name) for attendance_name in attendance_names]

    def test_cross_day_attendance_request_does_not_set_working_hours(self):
        attendance_request = self.make_attendance_request()
        attendance = self.get_request_attendance(attendance_request)

        self.assertEqual(attendance.status, "Present")
        self.assertFalse(attendance.working_hours)

    def test_multi_day_day_shift_request_does_not_set_working_hours(self):
        attendance_request = self.make_attendance_request(
            shift=self.day_shift.name,
            from_date=getdate(),
            to_date=add_days(getdate(), 2),
            custom_from_time="09:00:00",
            custom_to_time="18:00:00",
        )

        attendances = self.get_request_attendances(attendance_request)

        self.assertEqual(len(attendances), 3)
        for attendance in attendances:
            self.assertEqual(attendance.status, "Present")
            self.assertFalse(attendance.working_hours)

    def test_multi_day_cross_day_request_does_not_set_working_hours(self):
        attendance_request = self.make_attendance_request(
            from_date=getdate(),
            to_date=add_days(getdate(), 1),
        )

        attendances = self.get_request_attendances(attendance_request)

        self.assertEqual(len(attendances), 2)
        for attendance in attendances:
            self.assertEqual(attendance.status, "Present")
            self.assertFalse(attendance.working_hours)

    def test_full_day_request_updates_status_without_adding_existing_working_hours(self):
        self.make_attendance(status="Half Day", working_hours=7.0)

        attendance_request = self.make_attendance_request(
            shift=self.day_shift.name,
            custom_from_time="09:00:00",
            custom_to_time="18:00:00",
        )
        attendance = self.get_request_attendance(attendance_request)

        self.assertEqual(attendance.status, "Present")
        self.assertAlmostEqual(attendance.working_hours, 7.0)

    def test_opposite_half_day_request_with_leave_keeps_half_type_logic(self):
        leave_application = self.make_half_day_leave_application(custom_half_type="Second Half")

        attendance_request = self.make_attendance_request(
            shift=self.day_shift.name,
            custom_from_time="09:00:00",
            custom_to_time="13:00:00",
            half_day=1,
            half_day_date=getdate(),
            custom_half_type="First Half",
        )
        attendance = self.get_request_attendance(attendance_request)

        self.assertEqual(attendance.status, "Present")
        self.assertEqual(attendance.leave_application, leave_application.name)
        self.assertEqual(attendance.attendance_request, attendance_request.name)

    def test_closest_shift_prefers_cross_day_overlap_for_early_morning_request(self):
        with patch(
            "real_group_hrms.api.attendance_request.get_employee_allowed_shifts",
            return_value=[self.early_day_shift.name, self.cross_day_shift.name],
        ):
            shift_name = closest_shift_for_time(
                from_time="02:00:00",
                to_time="06:00:00",
                date=getdate(),
                employee=self.employee_name,
            )

        self.assertEqual(shift_name, self.cross_day_shift.name)

    def test_non_cross_day_request_rejects_reverse_time_window(self):
        with self.assertRaises(frappe.ValidationError):
            self.make_attendance_request(
                shift=self.day_shift.name,
                custom_from_time="18:00:00",
                custom_to_time="09:00:00",
            )

    def test_patch_corrects_existing_negative_cross_day_hours(self):
        attendance_request = self.make_attendance_request()
        attendance = self.get_request_attendance(attendance_request)

        frappe.db.set_value(
            "Attendance",
            attendance.name,
            {"working_hours": -16.0, "custom_working_hours": None},
            update_modified=False,
        )

        fix_cross_day_attendance_request_hours()

        attendance.reload()
        self.assertAlmostEqual(attendance.working_hours, 8.0)
