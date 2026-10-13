from datetime import date, datetime
from importlib import import_module
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch


day_wise_attendance = import_module(
    "real_group_hrms.real_group.report.[new]_day_wise_attendance.[new]_day_wise_attendance"
)
month_wise_attendance = import_module(
    "real_group_hrms.real_group.report.[new]_month_wise_attendance.[new]_month_wise_attendance"
)
monthly_attendance_report = import_module(
    "real_group_hrms.real_group.report.[new]_monthly_attendance_report.[new]_monthly_attendance_report"
)
form_14 = import_module("real_group_hrms.real_group.report.[new]_form_14.[new]_form_14")


def get_leave_type_doc(name):
    if name == "Compensatory Off":
        return SimpleNamespace(is_earned_leave=False, is_compensatory=True, is_lwp=False, name=name)
    if name == "Earned Leave - Plant":
        return SimpleNamespace(is_earned_leave=True, is_compensatory=False, is_lwp=False, name=name)
    if name == "Casual Leave - Plant":
        return SimpleNamespace(is_earned_leave=False, is_compensatory=False, is_lwp=False, name=name)
    if name == "Leave Without Pay":
        return SimpleNamespace(is_earned_leave=False, is_compensatory=False, is_lwp=True, name=name)
    raise AssertionError(f"Unexpected leave type requested in test: {name}")


class TestDayWiseAttendanceReport(TestCase):
    def setUp(self):
        self.target_date = date(2026, 1, 4)
        self.primary_application = SimpleNamespace(
            name="AP-LAP-PRIMARY",
            half_day=1,
            half_day_date=self.target_date,
            custom_half_type="Second Half",
        )
        self.primary_comp_off = get_leave_type_doc("Compensatory Off")

    def test_half_day_combo_ignores_rejected_earned_leave_with_approved_comp_off(self):
        other_leave = {
            "name": "AP-LAP-REJECTED-EL",
            "leave_type": "Earned Leave - Plant",
            "status": "Rejected",
            "docstatus": 0,
            "custom_half_type": "Second Half",
        }

        with patch.object(day_wise_attendance.frappe, "get_all", return_value=[other_leave]):
            result = day_wise_attendance.get_half_day_combo_status(
                "50010", self.target_date, self.primary_application, self.primary_comp_off
            )

        self.assertIsNone(result)

    def test_half_day_combo_ignores_rejected_casual_leave_with_approved_comp_off(self):
        other_leave = {
            "name": "AP-LAP-REJECTED-CL",
            "leave_type": "Casual Leave - Plant",
            "status": "Rejected",
            "docstatus": 0,
            "custom_half_type": "First Half",
        }

        with patch.object(day_wise_attendance.frappe, "get_all", return_value=[other_leave]):
            result = day_wise_attendance.get_half_day_combo_status(
                "50010", self.target_date, self.primary_application, self.primary_comp_off
            )

        self.assertIsNone(result)

    def test_half_day_combo_keeps_approved_earned_leave_with_approved_comp_off(self):
        other_leave = SimpleNamespace(
            name="AP-LAP-APPROVED-EL",
            leave_type="Earned Leave - Plant",
            status="Approved",
            docstatus=1,
            custom_half_type="First Half",
        )

        with patch.object(day_wise_attendance.frappe, "get_all", return_value=[other_leave]):
            with patch.object(
                day_wise_attendance.frappe,
                "get_cached_doc",
                side_effect=lambda _doctype, name: get_leave_type_doc(name),
            ):
                result = day_wise_attendance.get_half_day_combo_status(
                    "50010", self.target_date, self.primary_application, self.primary_comp_off
                )

        self.assertEqual(result, "ELCO")

    def test_get_status_treats_two_complementary_half_day_official_requests_as_od(self):
        target_date = date(2026, 3, 13)
        request_map = {
            "10079": {
                day_wise_attendance.format_date(target_date): [
                    day_wise_attendance.frappe._dict(
                        {
                            "name": "HR-ARQ-1",
                            "reason": "Official",
                            "half_day": 1,
                            "half_day_date": target_date,
                            "custom_half_type": "First Half",
                        }
                    ),
                    day_wise_attendance.frappe._dict(
                        {
                            "name": "HR-ARQ-2",
                            "reason": "Official",
                            "half_day": 1,
                            "half_day_date": target_date,
                            "custom_half_type": "Second Half",
                        }
                    ),
                ]
            }
        }
        data_on_date = {
            "attendance": [
                day_wise_attendance.frappe._dict(
                    {
                        "attendance_request": "HR-ARQ-2",
                        "leave_application": None,
                        "leave_type": None,
                        "custom_attendance_tag": "P",
                    }
                )
            ],
            "checkins": [],
        }

        with patch.object(
            day_wise_attendance.frappe,
            "get_cached_doc",
            return_value=SimpleNamespace(
                name="HR-ARQ-2",
                reason="Official",
                half_day=1,
                half_day_date=target_date,
                custom_half_type="Second Half",
            ),
        ):
            result = day_wise_attendance.get_status("10079", target_date, data_on_date, "P", request_map)

        self.assertEqual(result, "OD")

    def test_get_status_uses_approved_paid_half_when_other_half_is_lwp(self):
        target_date = date(2026, 5, 4)
        lwp_application = SimpleNamespace(
            name="RB-LAP-LWP",
            half_day=1,
            half_day_date=target_date,
            custom_half_type="Second Half",
            from_date=target_date,
            to_date=target_date,
        )
        other_leave = SimpleNamespace(
            name="RB-LAP-CL",
            leave_type="Casual Leave - Plant",
            status="Approved",
            docstatus=1,
            custom_half_type="First Half",
        )
        data_on_date = {
            "attendance": [
                day_wise_attendance.frappe._dict(
                    {
                        "leave_application": "RB-LAP-LWP",
                        "leave_type": "Leave Without Pay",
                        "attendance_request": None,
                        "custom_attendance_tag": "LWP",
                        "status": "Half Day",
                    }
                )
            ],
            "checkins": [],
        }

        def get_cached_doc(doctype, name):
            if doctype == "Leave Application":
                return lwp_application
            if doctype == "Leave Type":
                return get_leave_type_doc(name)
            raise AssertionError(f"Unexpected cached doc: {doctype} {name}")

        with (
            patch.object(day_wise_attendance.frappe, "get_cached_doc", side_effect=get_cached_doc),
            patch.object(day_wise_attendance.frappe, "get_all", return_value=[other_leave]),
            patch.object(day_wise_attendance, "is_holiday_for_employee", return_value={"is_holiday": False}),
        ):
            result = day_wise_attendance.get_status("12654", target_date, data_on_date, "LWP", {})

        self.assertEqual(result, "HCL")

    def test_get_status_uses_approved_od_half_when_other_half_is_lwp(self):
        target_date = date(2026, 5, 4)
        date_key = target_date.strftime("%d-%m-%Y")
        lwp_application = SimpleNamespace(
            name="RB-LAP-LWP",
            half_day=1,
            half_day_date=target_date,
            custom_half_type="Second Half",
            from_date=target_date,
            to_date=target_date,
        )
        request_map = {
            "12654": {
                date_key: [
                    day_wise_attendance.frappe._dict(
                        {
                            "name": "HR-ARQ-OD",
                            "reason": "Official",
                            "half_day": 1,
                            "half_day_date": target_date,
                            "custom_half_type": "First Half",
                            "docstatus": 1,
                        }
                    )
                ]
            }
        }
        data_on_date = {
            "attendance": [
                day_wise_attendance.frappe._dict(
                    {
                        "leave_application": "RB-LAP-LWP",
                        "leave_type": "Leave Without Pay",
                        "attendance_request": None,
                        "custom_attendance_tag": "LWP",
                        "status": "Half Day",
                    }
                )
            ],
            "checkins": [],
        }

        def get_cached_doc(doctype, name):
            if doctype == "Leave Application":
                return lwp_application
            if doctype == "Leave Type":
                return get_leave_type_doc(name)
            raise AssertionError(f"Unexpected cached doc: {doctype} {name}")

        with (
            patch.object(day_wise_attendance.frappe, "get_cached_doc", side_effect=get_cached_doc),
            patch.object(day_wise_attendance.frappe, "get_all", return_value=[]),
            patch.object(day_wise_attendance, "format_date", side_effect=lambda value: value.strftime("%d-%m-%Y")),
            patch.object(day_wise_attendance, "is_holiday_for_employee", return_value={"is_holiday": False}),
        ):
            result = day_wise_attendance.get_status("12654", target_date, data_on_date, "LWP", request_map)

        self.assertEqual(result, "HOD")

    def test_form14_places_approved_paid_half_against_lwp_half(self):
        target_date = date(2026, 5, 4)
        date_key = target_date.strftime("%d-%m-%Y")
        employee = day_wise_attendance.frappe._dict({"name": "12654"})
        lwp_application = SimpleNamespace(
            name="RB-LAP-LWP",
            half_day=1,
            half_day_date=target_date,
            custom_half_type="Second Half",
            from_date=target_date,
            to_date=target_date,
        )
        other_leave = SimpleNamespace(
            name="RB-LAP-CL",
            leave_type="Casual Leave - Plant",
            status="Approved",
            docstatus=1,
            custom_half_type="First Half",
        )
        attendance = day_wise_attendance.frappe._dict(
            {
                "employee": "12654",
                "attendance_date": target_date,
                "leave_application": "RB-LAP-LWP",
                "leave_type": "Leave Without Pay",
                "attendance_request": None,
                "custom_attendance_tag": "LWP",
                "status": "Half Day",
                "working_hours": 0.0,
                "shift": None,
            }
        )
        emp_data = {
            date_key: {
                "attendance": [attendance],
                "checkins": [],
            }
        }

        def get_cached_doc(doctype, name):
            if doctype == "Leave Application":
                return lwp_application
            if doctype == "Leave Type":
                return get_leave_type_doc(name)
            raise AssertionError(f"Unexpected cached doc: {doctype} {name}")

        with (
            patch.object(day_wise_attendance.frappe, "get_cached_doc", side_effect=get_cached_doc),
            patch.object(day_wise_attendance.frappe, "get_all", return_value=[other_leave]),
            patch.object(day_wise_attendance, "format_date", side_effect=lambda value: value.strftime("%d-%m-%Y")),
            patch.object(form_14, "format_date", side_effect=lambda value: value.strftime("%d-%m-%Y")),
            patch.object(day_wise_attendance, "is_holiday_for_employee", return_value={"is_holiday": False}),
            patch.object(form_14, "is_holiday_for_employee", return_value={"is_holiday": False}),
        ):
            snapshot = form_14.build_day_snapshot(employee, target_date, emp_data, {}, {})

        self.assertEqual(snapshot["processed_status"], "HCL")
        self.assertEqual(snapshot["first_half"], "CL")
        self.assertEqual(snapshot["second_half"], "A")

    def test_form14_places_approved_od_half_against_lwp_half(self):
        target_date = date(2026, 5, 4)
        date_key = target_date.strftime("%d-%m-%Y")
        employee = day_wise_attendance.frappe._dict({"name": "12654"})
        lwp_application = SimpleNamespace(
            name="RB-LAP-LWP",
            half_day=1,
            half_day_date=target_date,
            custom_half_type="Second Half",
            from_date=target_date,
            to_date=target_date,
        )
        attendance = day_wise_attendance.frappe._dict(
            {
                "employee": "12654",
                "attendance_date": target_date,
                "leave_application": "RB-LAP-LWP",
                "leave_type": "Leave Without Pay",
                "attendance_request": None,
                "custom_attendance_tag": "LWP",
                "status": "Half Day",
                "working_hours": 0.0,
                "shift": None,
            }
        )
        request_map = {
            "12654": {
                date_key: [
                    day_wise_attendance.frappe._dict(
                        {
                            "name": "HR-ARQ-OD",
                            "reason": "Official",
                            "half_day": 1,
                            "half_day_date": target_date,
                            "custom_half_type": "First Half",
                            "docstatus": 1,
                        }
                    )
                ]
            }
        }
        emp_data = {
            date_key: {
                "attendance": [attendance],
                "checkins": [],
            }
        }

        def get_cached_doc(doctype, name):
            if doctype == "Leave Application":
                return lwp_application
            if doctype == "Leave Type":
                return get_leave_type_doc(name)
            raise AssertionError(f"Unexpected cached doc: {doctype} {name}")

        with (
            patch.object(day_wise_attendance.frappe, "get_cached_doc", side_effect=get_cached_doc),
            patch.object(day_wise_attendance.frappe, "get_all", return_value=[]),
            patch.object(day_wise_attendance, "format_date", side_effect=lambda value: value.strftime("%d-%m-%Y")),
            patch.object(form_14, "format_date", side_effect=lambda value: value.strftime("%d-%m-%Y")),
            patch.object(day_wise_attendance, "is_holiday_for_employee", return_value={"is_holiday": False}),
            patch.object(form_14, "is_holiday_for_employee", return_value={"is_holiday": False}),
        ):
            snapshot = form_14.build_day_snapshot(employee, target_date, emp_data, request_map, {})

        self.assertEqual(snapshot["processed_status"], "HOD")
        self.assertEqual(snapshot["first_half"], "OD")
        self.assertEqual(snapshot["second_half"], "A")

    @patch.object(day_wise_attendance.frappe, "get_all")
    def test_day_wise_get_employees_excludes_records_outside_report_month(self, mock_get_all):
        mock_get_all.return_value = [
            {"name": "12500", "date_of_joining": date(2026, 1, 15), "relieving_date": None},
            {"name": "12501", "date_of_joining": date(2025, 1, 1), "relieving_date": date(2026, 1, 15)},
            {"name": "12799", "date_of_joining": date(2025, 1, 1), "relieving_date": date(2025, 12, 31)},
            {"name": "12800", "date_of_joining": date(2026, 2, 1), "relieving_date": None},
        ]

        employees = day_wise_attendance.get_employees(
            company="Real Ispat and Power Ltd",
            branch="Plant Site",
            division=None,
            department=None,
            employee=None,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        )

        self.assertEqual([employee["name"] for employee in employees], ["12500", "12501"])

    @patch.object(month_wise_attendance.frappe, "get_all")
    def test_month_wise_get_employees_returns_no_rows_for_future_joining_employee(self, mock_get_all):
        mock_get_all.return_value = [
            {"name": "12800", "date_of_joining": date(2026, 2, 1), "relieving_date": None}
        ]

        employees = month_wise_attendance.get_employees(
            company="Real Ispat and Power Ltd",
            branch="Plant Site",
            division=None,
            department=None,
            employee="12800",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            all_company=False,
        )

        self.assertEqual(employees, [])

    def test_month_wise_execute_handles_holiday_without_checkins(self):
        employee = day_wise_attendance.frappe._dict(
            {
                "name": "11742",
                "employee_name": "Pappu Nishad",
                "designation": "Electrician",
                "department": "Electrical - RIPL",
            }
        )
        attendance_map = {
            "11742": {
                "max_checkins": 0,
                "11-03-2026": {
                    "attendance": [
                        {
                            "working_hours": 0.0,
                            "custom_attendance_tag": "A",
                            "status": "Absent",
                            "shift": "N",
                        }
                    ],
                    "checkins": [],
                },
            }
        }
        summary_metrics = {fieldname: 0.0 for fieldname in month_wise_attendance.fieldnames}

        with (
            patch.object(month_wise_attendance.day_wise_attendance, "get_columns", return_value=[{"fieldname": "sr"}]),
            patch.object(month_wise_attendance.day_wise_attendance, "get_dates", return_value=[date(2026, 3, 11)]),
            patch.object(month_wise_attendance, "format_date", side_effect=lambda value: value.strftime("%d-%m-%Y")),
            patch.object(month_wise_attendance, "get_employees", return_value=[employee]),
            patch.object(month_wise_attendance.day_wise_attendance, "get_attendance", return_value=attendance_map),
            patch.object(month_wise_attendance.day_wise_attendance, "get_attendance_requests", return_value={}),
            patch.object(
                month_wise_attendance.day_wise_attendance,
                "get_shifts",
                return_value=[SimpleNamespace(name="N", custom_shift_time="12:00:00")],
            ),
            patch.object(
                month_wise_attendance.day_wise_attendance,
                "get_rows",
                return_value=(
                    [],
                    {"sr": "H Work"},
                    {"sr": "E Work"},
                    {"sr": "P Status"},
                    {"sr": "Status"},
                    {"sr": "Shift"},
                ),
            ),
            patch.object(month_wise_attendance.day_wise_attendance, "is_outside_service_period", return_value=False),
            patch.object(month_wise_attendance, "is_holiday_for_employee", return_value={"is_holiday": True}),
            patch.object(month_wise_attendance.day_wise_attendance, "get_status", return_value="A"),
            patch.object(month_wise_attendance.day_wise_attendance, "adjust_status_with_checkins", return_value="A"),
            patch.object(month_wise_attendance.day_wise_attendance, "has_mis_punch_request", return_value=False),
            patch.object(month_wise_attendance.day_wise_attendance, "derive_processed_status", return_value="A"),
            patch.object(month_wise_attendance, "calculate_summary_metrics", return_value=summary_metrics),
            patch.object(month_wise_attendance, "apply_summary_metrics"),
            patch.object(
                month_wise_attendance.day_wise_attendance, "get_holiday_extra_work", return_value=""
            ) as holiday_extra_work_mock,
        ):
            columns, data = month_wise_attendance.execute(
                {
                    "company": "Real Ispat and Power Ltd",
                    "branch": "Plant Site",
                    "month": "Mar",
                    "year": "2026",
                    "processed_attendance": 1,
                }
            )

        holiday_extra_work_mock.assert_called_once_with([])
        self.assertTrue(columns)
        self.assertTrue(data)

    def test_top_row_status_totals_include_new_holiday_weekly_off_leave_and_od_counts(self):
        totals = day_wise_attendance.init_top_row_status_totals()

        for status_code in ["HO", "WO", "HEL", "ODCL", "POW", "POD", "CLCO", "PHO"]:
            day_wise_attendance.add_top_row_status_totals(totals, status_code)

        self.assertEqual(
            totals,
            {
                "holiday": 1.5,
                "weekly_off": 2.0,
                "leaves": 2.0,
                "od": 1.0,
            },
        )

    def test_holiday_extra_work_returns_empty_when_checkins_are_missing(self):
        self.assertEqual(day_wise_attendance.get_holiday_extra_work([]), "")

    def test_holiday_extra_work_uses_first_and_last_checkin_when_available(self):
        checkins = [
            {"time": datetime(2026, 3, 11, 7, 56, 26)},
            {"time": datetime(2026, 3, 11, 20, 2, 30)},
        ]

        self.assertEqual(day_wise_attendance.get_holiday_extra_work(checkins), "12:06")

    def test_day_off_status_prefers_a1_for_sandwich_marked_attendance(self):
        attendance = day_wise_attendance.frappe._dict(
            {"custom_attendance_tag": "A", "custom_marked_absent_by_sandwich": 1}
        )

        with (
            patch.object(
                day_wise_attendance,
                "is_holiday_for_employee",
                return_value={"is_holiday": True, "is_weekly_off": True},
            ),
            patch.object(day_wise_attendance, "get_attendance_record", return_value=attendance),
        ):
            status = day_wise_attendance.get_employee_day_off_status("10794", date(2026, 2, 23), checkins=[])

        self.assertEqual(status, "A1")

    def test_day_off_status_uses_pow_when_checkins_exist_for_weekly_off(self):
        attendance = day_wise_attendance.frappe._dict(
            {"custom_attendance_tag": "WO", "custom_marked_absent_by_sandwich": 0}
        )

        with (
            patch.object(
                day_wise_attendance,
                "is_holiday_for_employee",
                return_value={"is_holiday": True, "is_weekly_off": True},
            ),
            patch.object(day_wise_attendance, "get_attendance_record", return_value=attendance),
        ):
            status = day_wise_attendance.get_employee_day_off_status(
                "10794",
                date(2026, 2, 16),
                checkins=[{"log_type": "IN"}, {"log_type": "OUT"}],
            )

        self.assertEqual(status, "POW")

    def test_derive_processed_status_keeps_pow_and_a1_codes(self):
        self.assertEqual(
            day_wise_attendance.derive_processed_status(
                "POW",
                "POW",
                None,
                [{"log_type": "IN"}, {"log_type": "OUT"}],
                9.0,
                {"is_holiday": True, "is_weekly_off": True},
            ),
            "POW",
        )
        self.assertEqual(
            day_wise_attendance.derive_processed_status(
                "A1",
                "A1",
                None,
                [],
                0.0,
                {"is_holiday": True, "is_weekly_off": True},
            ),
            "A1",
        )

    def test_day_wise_summary_uses_processed_status_when_processed_attendance_enabled(self):
        employee = day_wise_attendance.frappe._dict(
            {
                "name": "12005",
                "employee_name": "Rakesh Singh",
                "designation": "Supervisor",
                "department": "Security - RIPL",
            }
        )
        target_date = date(2026, 2, 1)
        attendance_map = {
            "12005": {
                "max_checkins": 0,
                "01-02-2026": {
                    "attendance": [],
                    "checkins": [],
                },
            }
        }

        with (
            patch.object(day_wise_attendance, "format_date", side_effect=lambda value: value.strftime("%d-%m-%Y")),
            patch.object(day_wise_attendance, "get_dates", return_value=[target_date]),
            patch.object(day_wise_attendance, "get_employees", return_value=[employee]),
            patch.object(day_wise_attendance, "get_attendance", return_value=attendance_map),
            patch.object(day_wise_attendance, "get_attendance_requests", return_value={}),
            patch.object(day_wise_attendance, "get_shifts", return_value=[]),
            patch.object(day_wise_attendance, "is_outside_service_period", return_value=False),
            patch.object(day_wise_attendance, "get_status", return_value="P"),
            patch.object(day_wise_attendance, "adjust_status_with_checkins", return_value="MIS"),
            patch.object(day_wise_attendance, "has_mis_punch_request", return_value=False),
            patch.object(day_wise_attendance, "derive_processed_status", return_value="P"),
            patch.object(day_wise_attendance, "is_holiday_for_employee", return_value={"is_holiday": False}),
        ):
            _, data = day_wise_attendance.execute(
                {
                    "company": "Real Ispat and Power Ltd",
                    "branch": "Plant Site",
                    "month": "Feb",
                    "year": "2026",
                    "employee": "12005",
                    "processed_attendance": 1,
                }
            )

        self.assertEqual(data[0]["05-02-2026"], "Present: 1")
        self.assertEqual(data[3]["01-02-2026"], "MIS")
        self.assertEqual(data[4]["01-02-2026"], "P")

    def test_monthly_attendance_report_uses_form14_od_to_match_paid_days(self):
        dates = [date(2026, 2, day) for day in range(1, 29)]
        request_map = {
            "12005": {
                "01-02-2026": [{"reason": "Official", "half_day": 0}],
                "02-02-2026": [{"reason": "Official", "half_day": 0}],
                "03-02-2026": [{"reason": "Official", "half_day": 0}],
                "04-02-2026": [{"reason": "Official", "half_day": 0}],
            }
        }
        raw_rows = [
            {
                "sr": "1",
                "token_no": "12005",
                "employee_name": "Rakesh Singh",
                "p": 21.0,
                "a": 0.0,
                "el": 0.0,
                "cl": 0.0,
                "co": 0.0,
                "od": 3.0,
                "ho": 0.0,
                "wo": 4.0,
                "ttl": 28.0,
                "m": 195,
            }
        ]

        def fake_getdate(value=None):
            if value is None:
                return dates[-1]
            return value

        with (
            patch.object(monthly_attendance_report.form, "execute", return_value=([], raw_rows)),
        ):
            _, data = monthly_attendance_report.execute(
                {
                    "company": "Real Ispat and Power Ltd",
                    "branch": "Plant Site",
                    "month": "Feb",
                    "year": "2026",
                    "employee": "12005",
                }
            )

        self.assertEqual(data[0]["total_present"], 21.0)
        self.assertEqual(data[0]["total_od"], 3.0)
        self.assertEqual(data[0]["total_wo"], 4.0)
        self.assertEqual(data[0]["total_ttl"], 28.0)
        self.assertNotIn("total_tour", data[0])

    def test_monthly_attendance_report_calculates_paid_days_from_visible_totals(self):
        self.assertEqual(
            monthly_attendance_report.calculate_paid_days(
                present=3.0,
                earned_leave=0.0,
                casual_leave=0.0,
                od=5.5,
                compensatory_off=0.0,
                holiday=0.0,
                weekly_off=1.0,
            ),
            9.5,
        )

    def test_day_off_status_keeps_leave_tag_even_when_sandwich_flag_is_set(self):
        attendance = day_wise_attendance.frappe._dict(
            {
                "custom_attendance_tag": "EL",
                "custom_marked_absent_by_sandwich": 1,
            }
        )

        with (
            patch.object(day_wise_attendance, "is_holiday_for_employee", return_value={"is_holiday": True}),
            patch.object(day_wise_attendance, "get_attendance_record", return_value=attendance),
        ):
            result = day_wise_attendance.get_employee_day_off_status("80008", date(2026, 2, 14), [])

        self.assertEqual(result, "EL")

    def test_day_off_status_returns_half_day_leave_tag_for_sandwich_leave(self):
        attendance = day_wise_attendance.frappe._dict(
            {
                "status": "Half Day",
                "custom_attendance_tag": "CL",
                "leave_application": "RB-LAP-24-0001447",
                "custom_marked_absent_by_sandwich": 1,
            }
        )
        leave_application = day_wise_attendance.frappe._dict(
            {
                "half_day": 1,
                "half_day_date": date(2026, 3, 31),
            }
        )

        with (
            patch.object(day_wise_attendance, "is_holiday_for_employee", return_value={"is_holiday": True}),
            patch.object(day_wise_attendance, "get_attendance_record", return_value=attendance),
            patch.object(day_wise_attendance.frappe, "get_cached_doc", return_value=leave_application),
        ):
            result = day_wise_attendance.get_employee_day_off_status("10568", date(2026, 3, 31), [])

        self.assertEqual(result, "HCL")

    def test_half_day_leave_processed_status_stays_hcl_for_single_mispunch(self):
        result = day_wise_attendance.derive_processed_status(
            "HCL",
            "HCL",
            day_wise_attendance.frappe._dict({}),
            [day_wise_attendance.frappe._dict({"time": datetime(2026, 2, 13, 6, 30)})],
            0.0,
            {"is_holiday": False},
        )

        self.assertEqual(result, "HCL")

    def test_half_day_leave_processed_status_stays_hcl_when_hours_below_half_day_threshold(self):
        attendance = day_wise_attendance.frappe._dict({"shift": "B"})
        checkins = [
            day_wise_attendance.frappe._dict({"time": datetime(2026, 4, 8, 14, 0), "log_type": "IN", "shift": "B"}),
            day_wise_attendance.frappe._dict({"time": datetime(2026, 4, 8, 17, 0), "log_type": "OUT", "shift": "B"}),
        ]

        with patch.object(
            day_wise_attendance.frappe,
            "get_cached_value",
            side_effect=["3:50:01"],
        ):
            result = day_wise_attendance.derive_processed_status(
                "HCL",
                "HCL",
                attendance,
                checkins,
                3.0,
                {"is_holiday": False},
            )

        self.assertEqual(result, "HCL")

    def test_half_day_leave_processed_status_becomes_pcl_when_hours_meet_half_day_threshold(self):
        attendance = day_wise_attendance.frappe._dict({"shift": "B"})
        checkins = [
            day_wise_attendance.frappe._dict({"time": datetime(2026, 4, 8, 14, 0), "log_type": "IN", "shift": "B"}),
            day_wise_attendance.frappe._dict({"time": datetime(2026, 4, 8, 18, 0), "log_type": "OUT", "shift": "B"}),
        ]

        with patch.object(
            day_wise_attendance.frappe,
            "get_cached_value",
            side_effect=["3:50:01"],
        ):
            result = day_wise_attendance.derive_processed_status(
                "HCL",
                "HCL",
                attendance,
                checkins,
                4.0,
                {"is_holiday": False},
            )

        self.assertEqual(result, "PCL")
