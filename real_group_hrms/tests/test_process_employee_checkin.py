from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe
from frappe.utils import get_datetime, get_time

from real_group_hrms.tasks import process_employee_checkin
from real_group_hrms.tasks.process_employee_checkin import (
    find_closest_shift_from_punch_time,
    get_checkout_validation_for_owning_shift,
    get_valid_owning_shift_for_checkout,
    process_employee_checkout,
)
from real_group_hrms.utils import convert_time_to_seconds


SITE_SHIFT_DEFINITIONS = [
    ("1", "11:00:00", "13:00:00", 0, "2:00:00"),
    ("2", "15:59:59", "23:59:59", 0, "7:45:00"),
    ("3", "9:00:00", "19:00:00", 0, "9:45:00"),
    ("5", "7:00:00", "19:00:00", 0, "11:30:00"),
    ("6", "12:00:00", "22:00:00", 0, "9:50:00"),
    ("7", "21:00:00", "6:00:00", 1, "8:45:00"),
    ("A", "6:00:00", "14:00:00", 0, "7:44:59"),
    ("B", "14:00:00", "22:00:00", 0, "7:44:59"),
    ("C", "22:00:00", "6:00:00", 1, "7:45:59"),
    ("D", "8:00:00", "20:00:00", 0, "11:30:00"),
    ("E", "9:00:00", "21:00:00", 0, "11:30:00"),
    ("F", "10:00:00", "19:00:00", 0, "8:45:00"),
    ("G", "9:00:00", "18:00:00", 0, "8:45:00"),
    ("I", "9:00:00", "20:00:00", 0, "10:45:00"),
    ("J", "7:00:00", "16:00:00", 0, "8:45:00"),
    ("K", "11:00:00", "20:00:00", 0, "8:45:00"),
    ("L", "10:00:00", "18:00:00", 0, "7:30:00"),
    ("M", "9:00:00", "18:00:00", 0, "6:30:00"),
    ("N", "20:00:00", "8:00:00", 1, "11:30:00"),
    ("O", "21:00:00", "9:00:00", 1, "11:30:00"),
    ("P", "9:00:00", "21:00:00", 0, "10:00:00"),
    ("Q", "9:30:00", "18:30:00", 0, "6:30:00"),
    ("R", "10:30:00", "19:00:00", 0, "6:30:00"),
    ("S", "10:00:00", "19:00:00", 0, "6:30:00"),
    ("S1", "10:00:00", "19:00:00", 0, "6:30:00"),
    ("T", "21:00:00", "8:00:00", 1, "10:45:00"),
    ("U", "8:00:00", "17:00:00", 0, "8:50:00"),
    ("V", "8:00:00", "18:00:00", 0, "9:45:00"),
    ("W", "9:00:00", "19:15:00", 0, "7:00:00"),
    ("X", "10:00:00", "22:00:00", 0, "11:29:00"),
    ("Y", "9:00:00", "18:30:00", 0, "7:00:00"),
    ("Z", "8:00:00", "15:30:00", 0, "6:00:00"),
]


class TestProcessEmployeeCheckin(TestCase):
    work_date = date(2026, 4, 5)

    def _build_owning_shift_data(self, shift_name, start_time, end_time, is_cross_day):
        shift_start = datetime.combine(self.work_date, get_time(start_time))
        shift_end_date = (
            self.work_date + timedelta(days=1) if is_cross_day else self.work_date
        )
        shift_end = datetime.combine(shift_end_date, get_time(end_time))

        return frappe._dict(
            {
                "shift": shift_name,
                "shift_start": shift_start,
                "shift_end": shift_end,
            }
        )

    def test_same_day_checkout_after_midnight_is_invalid_for_owning_shift(self):
        owning_shift_data = frappe._dict(
            {
                "shift": "A",
                "shift_start": get_datetime("2026-04-05 06:00:00"),
                "shift_end": get_datetime("2026-04-05 18:00:00"),
            }
        )

        with patch.object(
            process_employee_checkin,
            "get_shift_type",
            return_value=frappe._dict({"custom_is_cross_day": 0}),
        ):
            validation = get_checkout_validation_for_owning_shift(
                owning_shift_data, get_datetime("2026-04-06 00:02:00")
            )

        self.assertFalse(validation.is_valid)
        self.assertFalse(validation.is_cross_day)
        self.assertEqual(validation.valid_until, get_datetime("2026-04-06 00:00:00"))

    def test_same_day_early_checkin_and_late_same_day_checkout_is_still_valid(self):
        owning_shift_data = frappe._dict(
            {
                "shift": "A",
                "shift_start": get_datetime("2026-04-05 05:20:00"),
                "shift_end": get_datetime("2026-04-05 14:00:00"),
            }
        )

        with patch.object(
            process_employee_checkin,
            "get_shift_type",
            return_value=frappe._dict({"custom_is_cross_day": 0}),
        ):
            validation = get_checkout_validation_for_owning_shift(
                owning_shift_data, get_datetime("2026-04-05 23:58:00")
            )

        self.assertTrue(validation.is_valid)
        self.assertFalse(validation.is_cross_day)
        self.assertEqual(validation.valid_until, get_datetime("2026-04-06 00:00:00"))

    def test_same_day_missed_checkout_and_next_day_late_out_is_invalid(self):
        owning_shift_data = frappe._dict(
            {
                "shift": "U",
                "shift_start": get_datetime("2026-04-05 08:00:00"),
                "shift_end": get_datetime("2026-04-05 17:00:00"),
            }
        )

        with patch.object(
            process_employee_checkin,
            "get_shift_type",
            return_value=frappe._dict({"custom_is_cross_day": 0}),
        ):
            validation = get_checkout_validation_for_owning_shift(
                owning_shift_data, get_datetime("2026-04-06 08:10:00")
            )

        self.assertFalse(validation.is_valid)
        self.assertFalse(validation.is_cross_day)
        self.assertEqual(validation.valid_until, get_datetime("2026-04-06 00:00:00"))

    def test_cross_day_checkout_at_cutoff_is_valid_for_owning_shift(self):
        owning_shift_data = frappe._dict(
            {
                "shift": "7",
                "shift_start": get_datetime("2026-04-05 21:00:00"),
                "shift_end": get_datetime("2026-04-06 06:00:00"),
            }
        )

        with patch.object(
            process_employee_checkin,
            "get_shift_type",
            return_value=frappe._dict(
                {
                    "custom_is_cross_day": 1,
                    "custom_working_hours_threshold_for_present": "8:45:00",
                }
            ),
        ):
            validation = get_checkout_validation_for_owning_shift(
                owning_shift_data, get_datetime("2026-04-06 10:22:30")
            )

        self.assertTrue(validation.is_valid)
        self.assertTrue(validation.is_cross_day)
        self.assertEqual(validation.valid_until, get_datetime("2026-04-06 10:22:30"))

    def test_cross_day_early_checkout_before_shift_end_is_valid(self):
        owning_shift_data = frappe._dict(
            {
                "shift": "7",
                "shift_start": get_datetime("2026-04-05 21:00:00"),
                "shift_end": get_datetime("2026-04-06 06:00:00"),
            }
        )

        with patch.object(
            process_employee_checkin,
            "get_shift_type",
            return_value=frappe._dict(
                {
                    "custom_is_cross_day": 1,
                    "custom_working_hours_threshold_for_present": "8:45:00",
                }
            ),
        ):
            validation = get_checkout_validation_for_owning_shift(
                owning_shift_data, get_datetime("2026-04-06 05:10:00")
            )

        self.assertTrue(validation.is_valid)
        self.assertTrue(validation.is_cross_day)
        self.assertEqual(validation.valid_until, get_datetime("2026-04-06 10:22:30"))

    def test_cross_day_checkout_one_second_before_cutoff_is_valid(self):
        owning_shift_data = frappe._dict(
            {
                "shift": "7",
                "shift_start": get_datetime("2026-04-05 21:00:00"),
                "shift_end": get_datetime("2026-04-06 06:00:00"),
            }
        )

        with patch.object(
            process_employee_checkin,
            "get_shift_type",
            return_value=frappe._dict(
                {
                    "custom_is_cross_day": 1,
                    "custom_working_hours_threshold_for_present": "8:45:00",
                }
            ),
        ):
            validation = get_checkout_validation_for_owning_shift(
                owning_shift_data, get_datetime("2026-04-06 10:22:29")
            )

        self.assertTrue(validation.is_valid)
        self.assertTrue(validation.is_cross_day)
        self.assertEqual(validation.valid_until, get_datetime("2026-04-06 10:22:30"))

    def test_cross_day_checkout_after_cutoff_is_invalid_for_owning_shift(self):
        owning_shift_data = frappe._dict(
            {
                "shift": "7",
                "shift_start": get_datetime("2026-04-05 21:00:00"),
                "shift_end": get_datetime("2026-04-06 06:00:00"),
            }
        )

        with patch.object(
            process_employee_checkin,
            "get_shift_type",
            return_value=frappe._dict(
                {
                    "custom_is_cross_day": 1,
                    "custom_working_hours_threshold_for_present": "8:45:00",
                }
            ),
        ):
            validation = get_checkout_validation_for_owning_shift(
                owning_shift_data, get_datetime("2026-04-06 11:20:00")
            )

        self.assertFalse(validation.is_valid)
        self.assertTrue(validation.is_cross_day)
        self.assertEqual(validation.valid_until, get_datetime("2026-04-06 10:22:30"))

    def test_cross_day_checkout_one_second_after_cutoff_is_invalid(self):
        owning_shift_data = frappe._dict(
            {
                "shift": "7",
                "shift_start": get_datetime("2026-04-05 21:00:00"),
                "shift_end": get_datetime("2026-04-06 06:00:00"),
            }
        )

        with patch.object(
            process_employee_checkin,
            "get_shift_type",
            return_value=frappe._dict(
                {
                    "custom_is_cross_day": 1,
                    "custom_working_hours_threshold_for_present": "8:45:00",
                }
            ),
        ):
            validation = get_checkout_validation_for_owning_shift(
                owning_shift_data, get_datetime("2026-04-06 10:22:31")
            )

        self.assertFalse(validation.is_valid)
        self.assertTrue(validation.is_cross_day)
        self.assertEqual(validation.valid_until, get_datetime("2026-04-06 10:22:30"))

    def test_cross_day_missed_checkout_and_next_day_evening_out_is_invalid(self):
        owning_shift_data = frappe._dict(
            {
                "shift": "C",
                "shift_start": get_datetime("2026-04-05 22:00:00"),
                "shift_end": get_datetime("2026-04-06 06:00:00"),
            }
        )

        with patch.object(
            process_employee_checkin,
            "get_shift_type",
            return_value=frappe._dict(
                {
                    "custom_is_cross_day": 1,
                    "custom_working_hours_threshold_for_present": "7:45:59",
                }
            ),
        ):
            validation = get_checkout_validation_for_owning_shift(
                owning_shift_data, get_datetime("2026-04-06 18:00:00")
            )

        self.assertFalse(validation.is_valid)
        self.assertTrue(validation.is_cross_day)
        self.assertEqual(
            validation.valid_until,
            owning_shift_data.shift_end
            + timedelta(seconds=convert_time_to_seconds("7:45:59") / 2),
        )

    def test_multiple_outs_in_same_valid_same_day_window_all_validate_true(self):
        owning_shift_data = frappe._dict(
            {
                "shift": "G",
                "shift_start": get_datetime("2026-04-05 09:00:00"),
                "shift_end": get_datetime("2026-04-05 18:00:00"),
            }
        )

        with patch.object(
            process_employee_checkin,
            "get_shift_type",
            return_value=frappe._dict({"custom_is_cross_day": 0}),
        ):
            first_validation = get_checkout_validation_for_owning_shift(
                owning_shift_data, get_datetime("2026-04-05 18:05:00")
            )
            second_validation = get_checkout_validation_for_owning_shift(
                owning_shift_data, get_datetime("2026-04-05 22:30:00")
            )

        self.assertTrue(first_validation.is_valid)
        self.assertTrue(second_validation.is_valid)
        self.assertEqual(
            first_validation.valid_until, get_datetime("2026-04-06 00:00:00")
        )
        self.assertEqual(
            second_validation.valid_until, get_datetime("2026-04-06 00:00:00")
        )

    def test_multiple_outs_around_cross_day_expiry_first_valid_second_invalid(self):
        owning_shift_data = frappe._dict(
            {
                "shift": "7",
                "shift_start": get_datetime("2026-04-05 21:00:00"),
                "shift_end": get_datetime("2026-04-06 06:00:00"),
            }
        )

        shift_type = frappe._dict(
            {
                "custom_is_cross_day": 1,
                "custom_working_hours_threshold_for_present": "8:45:00",
            }
        )

        with patch.object(
            process_employee_checkin,
            "get_shift_type",
            return_value=shift_type,
        ):
            first_validation = get_checkout_validation_for_owning_shift(
                owning_shift_data, get_datetime("2026-04-06 10:00:00")
            )
            second_validation = get_checkout_validation_for_owning_shift(
                owning_shift_data, get_datetime("2026-04-06 11:00:00")
            )

        self.assertTrue(first_validation.is_valid)
        self.assertFalse(second_validation.is_valid)
        self.assertEqual(
            first_validation.valid_until, get_datetime("2026-04-06 10:22:30")
        )
        self.assertEqual(
            second_validation.valid_until, get_datetime("2026-04-06 10:22:30")
        )

    def test_all_site_shift_types_follow_checkout_expiry_rules(self):
        for (
            shift_name,
            start_time,
            end_time,
            is_cross_day,
            working_threshold,
        ) in SITE_SHIFT_DEFINITIONS:
            owning_shift_data = self._build_owning_shift_data(
                shift_name, start_time, end_time, is_cross_day
            )
            shift_type = frappe._dict(
                {
                    "custom_is_cross_day": is_cross_day,
                    "custom_working_hours_threshold_for_present": working_threshold,
                }
            )

            if is_cross_day:
                valid_until = owning_shift_data.shift_end + timedelta(
                    seconds=convert_time_to_seconds(working_threshold) / 2
                )
                valid_punch = valid_until
                invalid_punch = valid_until + timedelta(seconds=1)
            else:
                valid_until = datetime.combine(
                    self.work_date + timedelta(days=1), get_time("00:00:00")
                )
                valid_punch = datetime.combine(self.work_date, get_time("23:59:59"))
                invalid_punch = valid_until + timedelta(seconds=1)

            with self.subTest(shift=shift_name, case="valid"):
                with patch.object(
                    process_employee_checkin, "get_shift_type", return_value=shift_type
                ):
                    validation = get_checkout_validation_for_owning_shift(
                        owning_shift_data, valid_punch
                    )

                self.assertTrue(validation.is_valid)
                self.assertEqual(validation.is_cross_day, bool(is_cross_day))
                self.assertEqual(validation.valid_until, valid_until)

            with self.subTest(shift=shift_name, case="invalid"):
                with patch.object(
                    process_employee_checkin, "get_shift_type", return_value=shift_type
                ):
                    validation = get_checkout_validation_for_owning_shift(
                        owning_shift_data, invalid_punch
                    )

                self.assertFalse(validation.is_valid)
                self.assertEqual(validation.is_cross_day, bool(is_cross_day))
                self.assertEqual(validation.valid_until, valid_until)

    def test_same_day_expired_checkout_falls_back_to_next_day_shift(self):
        captured_docs = []
        fake_db = SimpleNamespace(
            exists=lambda *args, **kwargs: True, commit=lambda: None
        )

        class FakeCheckinDoc:
            def __init__(self, payload):
                self.payload = payload
                self.name = "CHK-0002"
                self.flags = SimpleNamespace()

            def insert(self):
                return self

        def fake_get_doc(*args, **kwargs):
            if args and args[0] == "Employee":
                return SimpleNamespace(grade="GR-01")
            if args and isinstance(args[0], dict):
                captured_docs.append(args[0])
                return FakeCheckinDoc(args[0])
            raise AssertionError(f"Unexpected get_doc args: {args!r}")

        log = frappe._dict(
            {
                "name": "BIO-0002",
                "employee": "EMP-0002",
                "employee_id": "EMP-0002",
                "punch_date": "2026-04-06",
                "punch_time": "00:25:00",
                "punch_direction": "O",
                "terminal_id": "TERM-01",
                "punch_datetime": datetime(2026, 4, 6, 0, 25, 0),
            }
        )

        with (
            patch.object(process_employee_checkin.frappe, "db", fake_db),
            patch.object(
                process_employee_checkin.frappe, "get_doc", side_effect=fake_get_doc
            ),
            patch.object(
                process_employee_checkin,
                "get_bio_log_filter_values",
                return_value={},
            ),
            patch.object(
                process_employee_checkin,
                "get_valid_owning_shift_for_checkout",
                return_value=frappe._dict(
                    {
                        "shift": "A",
                        "shift_start": get_datetime("2026-04-05 06:00:00"),
                        "shift_end": get_datetime("2026-04-05 14:00:00"),
                        "shift_actual_start": get_datetime("2026-04-05 05:30:00"),
                        "shift_actual_end": get_datetime("2026-04-05 14:30:00"),
                    }
                ),
            ),
            patch.object(
                process_employee_checkin,
                "get_checkout_validation_for_owning_shift",
                return_value=frappe._dict({"is_valid": False}),
            ),
            patch.object(
                process_employee_checkin,
                "get_employee_allowed_shifts",
                return_value=["A", "C", "G"],
            ),
            patch.object(
                process_employee_checkin,
                "find_closest_shift_from_punch_time",
                return_value="C",
            ),
            patch.object(
                process_employee_checkin,
                "get_shift_type",
                return_value=frappe._dict({"custom_is_cross_day": 1}),
            ),
            patch.object(
                process_employee_checkin,
                "fetch_shift_details",
                return_value=SimpleNamespace(
                    start_datetime=get_datetime("2026-04-06 22:00:00"),
                    end_datetime=get_datetime("2026-04-07 06:00:00"),
                    actual_start=get_datetime("2026-04-06 21:30:00"),
                    actual_end=get_datetime("2026-04-07 06:30:00"),
                ),
            ),
            patch.object(
                process_employee_checkin,
                "mark_bio_log",
                return_value=None,
            ),
            patch.object(
                process_employee_checkin,
                "get_link_to_form",
                side_effect=lambda doctype, name: f"{doctype}:{name}",
            ),
        ):
            process_employee_checkout([log])

        self.assertEqual(len(captured_docs), 1)
        self.assertEqual(captured_docs[0]["shift"], "C")
        self.assertEqual(captured_docs[0]["log_type"], "OUT")

    def test_process_employee_checkout_falls_back_when_owning_shift_is_expired(self):
        captured_docs = []
        fake_db = SimpleNamespace(
            exists=lambda *args, **kwargs: True, commit=lambda: None
        )

        class FakeCheckinDoc:
            def __init__(self, payload):
                self.payload = payload
                self.name = "CHK-0001"
                self.flags = SimpleNamespace()

            def insert(self):
                return self

        def fake_get_doc(*args, **kwargs):
            if args and args[0] == "Employee":
                return SimpleNamespace(grade="GR-01")
            if args and isinstance(args[0], dict):
                captured_docs.append(args[0])
                return FakeCheckinDoc(args[0])
            raise AssertionError(f"Unexpected get_doc args: {args!r}")

        log = frappe._dict(
            {
                "name": "BIO-0001",
                "employee": "EMP-0001",
                "employee_id": "EMP-0001",
                "punch_date": "2026-04-06",
                "punch_time": "11:20:00",
                "punch_direction": "O",
                "terminal_id": "TERM-01",
                "punch_datetime": datetime(2026, 4, 6, 11, 20, 0),
            }
        )

        with (
            patch.object(process_employee_checkin.frappe, "db", fake_db),
            patch.object(
                process_employee_checkin.frappe, "get_doc", side_effect=fake_get_doc
            ),
            patch.object(
                process_employee_checkin,
                "get_bio_log_filter_values",
                return_value={},
            ),
            patch.object(
                process_employee_checkin,
                "get_valid_owning_shift_for_checkout",
                return_value=frappe._dict(
                    {
                        "shift": "7",
                        "shift_start": get_datetime("2026-04-05 21:00:00"),
                        "shift_end": get_datetime("2026-04-06 06:00:00"),
                        "shift_actual_start": get_datetime("2026-04-05 20:30:00"),
                        "shift_actual_end": get_datetime("2026-04-06 06:30:00"),
                    }
                ),
            ),
            patch.object(
                process_employee_checkin,
                "get_checkout_validation_for_owning_shift",
                return_value=frappe._dict({"is_valid": False}),
            ),
            patch.object(
                process_employee_checkin,
                "get_employee_allowed_shifts",
                return_value=["A", "7"],
            ),
            patch.object(
                process_employee_checkin,
                "find_closest_shift_from_punch_time",
                return_value="A",
            ),
            patch.object(
                process_employee_checkin,
                "get_shift_type",
                return_value=frappe._dict({"custom_is_cross_day": 0}),
            ),
            patch.object(
                process_employee_checkin,
                "fetch_shift_details",
                return_value=SimpleNamespace(
                    start_datetime=get_datetime("2026-04-06 06:00:00"),
                    end_datetime=get_datetime("2026-04-06 14:00:00"),
                    actual_start=get_datetime("2026-04-06 05:30:00"),
                    actual_end=get_datetime("2026-04-06 14:30:00"),
                ),
            ),
            patch.object(
                process_employee_checkin,
                "mark_bio_log",
                return_value=None,
            ),
            patch.object(
                process_employee_checkin,
                "get_link_to_form",
                side_effect=lambda doctype, name: f"{doctype}:{name}",
            ),
        ):
            process_employee_checkout([log])

        self.assertEqual(len(captured_docs), 1)
        self.assertEqual(captured_docs[0]["shift"], "A")
        self.assertEqual(captured_docs[0]["log_type"], "OUT")

    def test_process_employee_checkout_uses_fallback_when_no_owning_shift_exists(self):
        captured_docs = []
        marked_logs = []

        fake_db = SimpleNamespace(
            exists=lambda *args, **kwargs: True,
            commit=lambda: None,
        )

        class FakeCheckinDoc:
            def __init__(self, payload):
                self.payload = payload
                self.name = "CHK-0100"
                self.flags = SimpleNamespace()

            def insert(self):
                return self

        def fake_get_doc(*args, **kwargs):
            if args and args[0] == "Employee":
                return SimpleNamespace(grade="GR-01")
            if args and isinstance(args[0], dict):
                captured_docs.append(args[0])
                return FakeCheckinDoc(args[0])
            raise AssertionError(f"Unexpected get_doc args: {args!r}")

        def fake_mark_bio_log(log_name, status, message, filter_values=None):
            marked_logs.append(
                {
                    "log_name": log_name,
                    "status": status,
                    "message": message,
                    "filter_values": filter_values,
                }
            )

        log = frappe._dict(
            {
                "name": "BIO-0100",
                "employee": "EMP-0100",
                "employee_id": "EMP-0100",
                "punch_date": "2026-04-06",
                "punch_time": "18:05:00",
                "punch_direction": "O",
                "terminal_id": "TERM-01",
                "punch_datetime": datetime(2026, 4, 6, 18, 5, 0),
            }
        )

        with (
            patch.object(process_employee_checkin.frappe, "db", fake_db),
            patch.object(
                process_employee_checkin.frappe, "get_doc", side_effect=fake_get_doc
            ),
            patch.object(
                process_employee_checkin,
                "get_bio_log_filter_values",
                return_value={},
            ),
            patch.object(
                process_employee_checkin,
                "get_valid_owning_shift_for_checkout",
                return_value=None,
            ),
            patch.object(
                process_employee_checkin,
                "get_employee_allowed_shifts",
                return_value=["G", "U"],
            ),
            patch.object(
                process_employee_checkin,
                "find_closest_shift_from_punch_time",
                return_value="G",
            ),
            patch.object(
                process_employee_checkin,
                "get_shift_type",
                return_value=frappe._dict({"custom_is_cross_day": 0}),
            ),
            patch.object(
                process_employee_checkin,
                "fetch_shift_details",
                return_value=SimpleNamespace(
                    start_datetime=get_datetime("2026-04-06 09:00:00"),
                    end_datetime=get_datetime("2026-04-06 18:00:00"),
                    actual_start=get_datetime("2026-04-06 08:30:00"),
                    actual_end=get_datetime("2026-04-06 18:30:00"),
                ),
            ),
            patch.object(
                process_employee_checkin,
                "mark_bio_log",
                side_effect=fake_mark_bio_log,
            ),
            patch.object(
                process_employee_checkin,
                "get_link_to_form",
                side_effect=lambda doctype, name: f"{doctype}:{name}",
            ),
        ):
            process_employee_checkout([log])

        self.assertEqual(len(captured_docs), 1)
        self.assertEqual(captured_docs[0]["shift"], "G")
        self.assertEqual(captured_docs[0]["log_type"], "OUT")
        self.assertEqual(len(marked_logs), 1)
        self.assertEqual(marked_logs[0]["status"], "Y")

    def test_process_employee_checkout_marks_error_when_punch_datetime_missing(self):
        marked_logs = []

        fake_db = SimpleNamespace(
            exists=lambda *args, **kwargs: True,
            commit=lambda: None,
        )

        def fake_mark_bio_log(log_name, status, message, filter_values=None):
            marked_logs.append(
                {
                    "log_name": log_name,
                    "status": status,
                    "message": message,
                    "filter_values": filter_values,
                }
            )

        log = frappe._dict(
            {
                "name": "BIO-0101",
                "employee": "EMP-0101",
                "employee_id": "EMP-0101",
                "punch_date": None,
                "punch_time": None,
                "punch_direction": "O",
                "terminal_id": "TERM-01",
                "punch_datetime": None,
            }
        )

        with (
            patch.object(process_employee_checkin.frappe, "db", fake_db),
            patch.object(
                process_employee_checkin.frappe,
                "get_doc",
                return_value=SimpleNamespace(grade="GR-01"),
            ),
            patch.object(
                process_employee_checkin,
                "get_bio_log_filter_values",
                return_value={},
            ),
            patch.object(
                process_employee_checkin,
                "mark_bio_log",
                side_effect=fake_mark_bio_log,
            ),
            patch.object(
                process_employee_checkin,
                "get_link_to_form",
                side_effect=lambda doctype, name: f"{doctype}:{name}",
            ),
        ):
            process_employee_checkout([log])

        self.assertEqual(len(marked_logs), 1)
        self.assertEqual(marked_logs[0]["status"], "E")
        self.assertIn("Missing punch date/time", marked_logs[0]["message"])

    def test_process_employee_checkout_duplicate_bio_log_is_reported(self):
        marked_logs = []

        fake_db = SimpleNamespace(
            exists=lambda *args, **kwargs: True,
            commit=lambda: None,
            get_value=lambda doctype, filters, fieldname=None, order_by=None: (
                "CHK-EXIST-1" if doctype == "Employee Checkin" else None
            ),
        )

        class FakeDuplicateCheckinDoc:
            def __init__(self, payload):
                self.payload = payload
                self.flags = SimpleNamespace()
                self.name = "CHK-DUP"

            def insert(self):
                raise Exception(
                    "Duplicate entry 'BIO-0102' for key 'custom_bio_log_id'"
                )

        def fake_get_doc(*args, **kwargs):
            if args and args[0] == "Employee":
                return SimpleNamespace(grade="GR-01")
            if args and isinstance(args[0], dict):
                return FakeDuplicateCheckinDoc(args[0])
            raise AssertionError(f"Unexpected get_doc args: {args!r}")

        def fake_mark_bio_log(log_name, status, message, filter_values=None):
            marked_logs.append(
                {
                    "log_name": log_name,
                    "status": status,
                    "message": message,
                    "filter_values": filter_values,
                }
            )

        log = frappe._dict(
            {
                "name": "BIO-0102",
                "employee": "EMP-0102",
                "employee_id": "EMP-0102",
                "punch_date": "2026-04-06",
                "punch_time": "18:05:00",
                "punch_direction": "O",
                "terminal_id": "TERM-01",
                "punch_datetime": datetime(2026, 4, 6, 18, 5, 0),
            }
        )

        with (
            patch.object(process_employee_checkin.frappe, "db", fake_db),
            patch.object(
                process_employee_checkin.frappe, "get_doc", side_effect=fake_get_doc
            ),
            patch.object(
                process_employee_checkin,
                "get_bio_log_filter_values",
                return_value={},
            ),
            patch.object(
                process_employee_checkin,
                "get_valid_owning_shift_for_checkout",
                return_value=None,
            ),
            patch.object(
                process_employee_checkin,
                "get_employee_allowed_shifts",
                return_value=["G"],
            ),
            patch.object(
                process_employee_checkin,
                "find_closest_shift_from_punch_time",
                return_value="G",
            ),
            patch.object(
                process_employee_checkin,
                "get_shift_type",
                return_value=frappe._dict({"custom_is_cross_day": 0}),
            ),
            patch.object(
                process_employee_checkin,
                "fetch_shift_details",
                return_value=SimpleNamespace(
                    start_datetime=get_datetime("2026-04-06 09:00:00"),
                    end_datetime=get_datetime("2026-04-06 18:00:00"),
                    actual_start=get_datetime("2026-04-06 08:30:00"),
                    actual_end=get_datetime("2026-04-06 18:30:00"),
                ),
            ),
            patch.object(
                process_employee_checkin,
                "mark_bio_log",
                side_effect=fake_mark_bio_log,
            ),
            patch.object(
                process_employee_checkin,
                "get_link_to_form",
                side_effect=lambda doctype, name: f"{doctype}:{name}",
            ),
        ):
            process_employee_checkout([log])

        self.assertEqual(len(marked_logs), 1)
        self.assertEqual(marked_logs[0]["status"], "E")
        self.assertIn("Bio log already linked", marked_logs[0]["message"])
        self.assertIn("CHK-EXIST-1", marked_logs[0]["message"])

    def test_find_closest_shift_from_punch_time_uses_start_for_in(self):
        shifts = [
            frappe._dict(
                {
                    "name": "A",
                    "start_time": "06:00:00",
                    "end_time": "14:00:00",
                    "custom_is_cross_day": 0,
                    "custom_early_entry_grace_period": 0,
                    "custom_late_exit_grace_period": 0,
                }
            ),
            frappe._dict(
                {
                    "name": "G",
                    "start_time": "09:00:00",
                    "end_time": "18:00:00",
                    "custom_is_cross_day": 0,
                    "custom_early_entry_grace_period": 0,
                    "custom_late_exit_grace_period": 0,
                }
            ),
        ]

        fake_db = SimpleNamespace(get_all=lambda *args, **kwargs: shifts)

        def fake_get_shift_timings(shift, punch_dt, grade=None, is_checkout=False):
            work_date = punch_dt.date()
            start_dt = datetime.combine(work_date, get_time(shift.start_time))
            end_dt = datetime.combine(work_date, get_time(shift.end_time))
            return start_dt, end_dt

        with (
            patch.object(process_employee_checkin.frappe, "db", fake_db),
            patch.object(
                process_employee_checkin,
                "get_shift_timings",
                side_effect=fake_get_shift_timings,
            ),
        ):
            shift = find_closest_shift_from_punch_time(
                ["A", "G"],
                datetime(2026, 4, 6, 8, 50, 0),
                date=date(2026, 4, 6),
                log_type="IN",
                direction_hint="I",
            )

        self.assertEqual(shift, "G")

    def test_find_closest_shift_from_punch_time_uses_end_for_out(self):
        shifts = [
            frappe._dict(
                {
                    "name": "A",
                    "start_time": "06:00:00",
                    "end_time": "14:00:00",
                    "custom_is_cross_day": 0,
                    "custom_early_entry_grace_period": 0,
                    "custom_late_exit_grace_period": 0,
                }
            ),
            frappe._dict(
                {
                    "name": "G",
                    "start_time": "09:00:00",
                    "end_time": "18:00:00",
                    "custom_is_cross_day": 0,
                    "custom_early_entry_grace_period": 0,
                    "custom_late_exit_grace_period": 0,
                }
            ),
        ]

        fake_db = SimpleNamespace(get_all=lambda *args, **kwargs: shifts)

        def fake_get_shift_timings(shift, punch_dt, grade=None, is_checkout=False):
            work_date = punch_dt.date()
            start_dt = datetime.combine(work_date, get_time(shift.start_time))
            end_dt = datetime.combine(work_date, get_time(shift.end_time))
            return start_dt, end_dt

        with (
            patch.object(process_employee_checkin.frappe, "db", fake_db),
            patch.object(
                process_employee_checkin,
                "get_shift_timings",
                side_effect=fake_get_shift_timings,
            ),
        ):
            shift = find_closest_shift_from_punch_time(
                ["A", "G"],
                datetime(2026, 4, 6, 17, 50, 0),
                date=date(2026, 4, 6),
                log_type="OUT",
                direction_hint="O",
            )

        self.assertEqual(shift, "G")

    def test_get_valid_owning_shift_for_checkout_ignores_ins_before_latest_out(self):
        fake_latest_out = get_datetime("2026-04-05 18:00:00")
        captured_filters = {}

        fake_db = SimpleNamespace(
            get_value=lambda doctype, filters=None, fieldname=None, order_by=None: (
                fake_latest_out if doctype == "Employee Checkin" else None
            )
        )

        def fake_get_all(
            doctype, filters=None, fields=None, order_by=None, limit_page_length=None
        ):
            captured_filters["filters"] = filters
            return [
                frappe._dict(
                    {
                        "name": "CHK-IN-NEW",
                        "shift": "G",
                        "shift_start": get_datetime("2026-04-05 09:00:00"),
                        "shift_end": get_datetime("2026-04-05 18:00:00"),
                        "shift_actual_start": get_datetime("2026-04-05 08:30:00"),
                        "shift_actual_end": get_datetime("2026-04-05 18:30:00"),
                        "time": get_datetime("2026-04-05 19:00:00"),
                    }
                )
            ]

        with (
            patch.object(process_employee_checkin.frappe, "db", fake_db),
            patch.object(
                process_employee_checkin.frappe,
                "get_all",
                side_effect=fake_get_all,
            ),
        ):
            result = get_valid_owning_shift_for_checkout(
                "EMP-0200",
                get_datetime("2026-04-05 22:00:00"),
                "GR-01",
            )

        self.assertIsNotNone(result)
        self.assertEqual(result.shift, "G")
        self.assertIn(["time", ">", fake_latest_out], captured_filters["filters"])

    def test_get_valid_owning_shift_for_checkout_returns_none_when_no_candidate_in(
        self,
    ):
        fake_db = SimpleNamespace(get_value=lambda *args, **kwargs: None)

        with (
            patch.object(process_employee_checkin.frappe, "db", fake_db),
            patch.object(
                process_employee_checkin.frappe,
                "get_all",
                return_value=[],
            ),
        ):
            result = get_valid_owning_shift_for_checkout(
                "EMP-0201",
                get_datetime("2026-04-05 22:00:00"),
                "GR-01",
            )

        self.assertIsNone(result)

    def test_cross_day_expired_checkout_falls_back_to_day_shift(self):
        captured_docs = []
        fake_db = SimpleNamespace(
            exists=lambda *args, **kwargs: True, commit=lambda: None
        )

        class FakeCheckinDoc:
            def __init__(self, payload):
                self.payload = payload
                self.name = "CHK-0003"
                self.flags = SimpleNamespace()

            def insert(self):
                return self

        def fake_get_doc(*args, **kwargs):
            if args and args[0] == "Employee":
                return SimpleNamespace(grade="GR-01")
            if args and isinstance(args[0], dict):
                captured_docs.append(args[0])
                return FakeCheckinDoc(args[0])
            raise AssertionError(f"Unexpected get_doc args: {args!r}")

        log = frappe._dict(
            {
                "name": "BIO-0003",
                "employee": "EMP-0003",
                "employee_id": "EMP-0003",
                "punch_date": "2026-04-06",
                "punch_time": "11:00:00",
                "punch_direction": "O",
                "terminal_id": "TERM-01",
                "punch_datetime": datetime(2026, 4, 6, 11, 0, 0),
            }
        )

        with (
            patch.object(process_employee_checkin.frappe, "db", fake_db),
            patch.object(
                process_employee_checkin.frappe, "get_doc", side_effect=fake_get_doc
            ),
            patch.object(
                process_employee_checkin,
                "get_bio_log_filter_values",
                return_value={},
            ),
            patch.object(
                process_employee_checkin,
                "get_valid_owning_shift_for_checkout",
                return_value=frappe._dict(
                    {
                        "shift": "7",
                        "shift_start": get_datetime("2026-04-05 21:00:00"),
                        "shift_end": get_datetime("2026-04-06 06:00:00"),
                        "shift_actual_start": get_datetime("2026-04-05 20:30:00"),
                        "shift_actual_end": get_datetime("2026-04-06 06:30:00"),
                    }
                ),
            ),
            patch.object(
                process_employee_checkin,
                "get_checkout_validation_for_owning_shift",
                return_value=frappe._dict({"is_valid": False}),
            ),
            patch.object(
                process_employee_checkin,
                "get_employee_allowed_shifts",
                return_value=["A", "7"],
            ),
            patch.object(
                process_employee_checkin,
                "find_closest_shift_from_punch_time",
                return_value="A",
            ),
            patch.object(
                process_employee_checkin,
                "get_shift_type",
                return_value=frappe._dict({"custom_is_cross_day": 0}),
            ),
            patch.object(
                process_employee_checkin,
                "fetch_shift_details",
                return_value=SimpleNamespace(
                    start_datetime=get_datetime("2026-04-06 06:00:00"),
                    end_datetime=get_datetime("2026-04-06 14:00:00"),
                    actual_start=get_datetime("2026-04-06 05:30:00"),
                    actual_end=get_datetime("2026-04-06 14:30:00"),
                ),
            ),
            patch.object(
                process_employee_checkin,
                "mark_bio_log",
                return_value=None,
            ),
            patch.object(
                process_employee_checkin,
                "get_link_to_form",
                side_effect=lambda doctype, name: f"{doctype}:{name}",
            ),
        ):
            process_employee_checkout([log])

        self.assertEqual(len(captured_docs), 1)
        self.assertEqual(captured_docs[0]["shift"], "A")
        self.assertEqual(captured_docs[0]["log_type"], "OUT")
