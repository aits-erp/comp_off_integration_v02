from datetime import date, datetime, time
from importlib import import_module
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch


form_14 = import_module("real_group_hrms.real_group.report.[new]_form_14.[new]_form_14")


class TestForm14Report(TestCase):
    @patch.object(form_14.frappe, "get_all")
    def test_get_employees_for_period_sorts_by_numeric_employee_id(self, mock_get_all):
        mock_get_all.return_value = [
            {"name": "12292", "date_of_joining": None, "relieving_date": None},
            {"name": "2", "date_of_joining": None, "relieving_date": None},
            {"name": "11941", "date_of_joining": None, "relieving_date": None},
        ]

        employees = form_14.get_employees_for_period(
            company="Real Ispat and Power Ltd",
            branch="Corporate Office",
            division=None,
            department=None,
            employee=None,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        )

        self.assertEqual([employee["name"] for employee in employees], ["2", "11941", "12292"])

    @patch.object(form_14.frappe, "get_all")
    def test_get_employees_for_period_excludes_records_outside_report_month(self, mock_get_all):
        mock_get_all.return_value = [
            {"name": "12500", "date_of_joining": date(2026, 1, 15), "relieving_date": None},
            {"name": "12501", "date_of_joining": date(2025, 1, 1), "relieving_date": date(2026, 1, 15)},
            {"name": "12799", "date_of_joining": date(2025, 1, 1), "relieving_date": date(2025, 12, 31)},
            {"name": "12800", "date_of_joining": date(2026, 2, 1), "relieving_date": None},
        ]

        employees = form_14.get_employees_for_period(
            company="Real Ispat and Power Ltd",
            branch="Plant Site",
            division=None,
            department=None,
            employee=None,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        )

        self.assertEqual([employee["name"] for employee in employees], ["12500", "12501"])

    @patch.object(form_14.frappe, "get_all")
    def test_get_employees_for_period_returns_no_rows_for_future_joining_employee(self, mock_get_all):
        mock_get_all.return_value = [
            {"name": "12800", "date_of_joining": date(2026, 2, 1), "relieving_date": None}
        ]

        employees = form_14.get_employees_for_period(
            company="Real Ispat and Power Ltd",
            branch="Plant Site",
            division=None,
            department=None,
            employee="12800",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        )

        self.assertEqual(employees, [])

    def test_processed_half_day_leave_without_half_type_uses_presence_side(self):
        checkins = [SimpleNamespace(time=datetime(2026, 1, 8, 14, 5, 26))]

        result = form_14.map_status_to_halves("PEL", "HEL", checkins, 4.34, False, None)

        self.assertEqual(result, ("EL", "P"))

    def test_half_day_leave_without_half_type_handles_first_half_presence(self):
        checkins = [SimpleNamespace(time=datetime(2026, 1, 8, 9, 0, 0))]

        result = form_14.map_status_to_halves("PCL", "HCL", checkins, 4.0, False, None)

        self.assertEqual(result, ("P", "CL"))

    def test_half_day_leave_with_second_half_type_and_single_mispunch_keeps_absent_first_half(self):
        checkins = [SimpleNamespace(time=datetime(2026, 3, 3, 9, 59, 48))]

        result = form_14.map_status_to_halves("HCL", "HCL", checkins, 0.0, False, "Second Half")

        self.assertEqual(result, ("A", "CL"))

    def test_optional_leave_half_without_half_type_does_not_crash(self):
        checkins = [SimpleNamespace(time=datetime(2026, 1, 26, 9, 0, 0))]

        result = form_14.map_status_to_halves("ELHO", "ELHO", checkins, 4.0, {"is_holiday": 1}, None)

        self.assertEqual(result, ("P", "EL"))

    def test_half_day_uses_in_punch_to_place_presence_on_second_half_for_night_shift(self):
        checkins = [
            SimpleNamespace(time=datetime(2026, 3, 25, 22, 23, 14), log_type="IN"),
            SimpleNamespace(time=datetime(2026, 3, 26, 6, 0, 58), log_type="OUT"),
        ]

        result = form_14.map_status_to_halves("HD", "HD", checkins, 7.63, False, None)

        self.assertEqual(result, ("A", "P"))

    def test_derive_half_day_present_half_uses_shift_boundary_for_day_shift(self):
        attendance = {"in_time": datetime(2026, 3, 19, 12, 56, 22)}
        checkins = [
            SimpleNamespace(
                time=datetime(2026, 3, 19, 12, 56, 22),
                log_type="IN",
                shift_start=datetime(2026, 3, 19, 10, 0, 0),
            )
        ]
        shift_map = {
            "F": SimpleNamespace(
                custom_working_hours_threshold_for_half_day="4:00:00",
                custom_half_day_threshold="4:00:00",
                start_time=time(10, 0, 0),
            )
        }

        result = form_14.derive_half_day_present_half(attendance, checkins, "F", shift_map)

        self.assertEqual(result, "Second Half")

    def test_derive_half_day_present_half_handles_cross_midnight_shift(self):
        attendance = {"in_time": datetime(2026, 3, 26, 0, 35, 0)}
        checkins = [
            SimpleNamespace(
                time=datetime(2026, 3, 26, 0, 35, 0),
                log_type="IN",
                shift_start=datetime(2026, 3, 25, 22, 0, 0),
            )
        ]
        shift_map = {
            "C": SimpleNamespace(
                custom_working_hours_threshold_for_half_day="4:00:00",
                custom_half_day_threshold="4:00:00",
                start_time=time(22, 0, 0),
            )
        }

        result = form_14.derive_half_day_present_half(attendance, checkins, "C", shift_map)

        self.assertEqual(result, "Second Half")

    def test_processed_first_half_official_keeps_od_on_first_half(self):
        checkins = [
            SimpleNamespace(time=datetime(2026, 3, 25, 22, 23, 14), log_type="IN"),
            SimpleNamespace(time=datetime(2026, 3, 26, 6, 0, 58), log_type="OUT"),
        ]

        result = form_14.map_status_to_halves("POD", "HOD", checkins, 7.63, False, "First Half")

        self.assertEqual(result, ("OD", "P"))

    def test_rebalance_presence_halves_handles_empty_pair(self):
        self.assertEqual(form_14.rebalance_presence_halves(None, False), ("", ""))
