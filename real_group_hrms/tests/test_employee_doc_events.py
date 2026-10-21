from datetime import date
from importlib import import_module
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

employee = import_module("real_group_hrms.doc_events.employee")


class TestEmployeeDocEvents(TestCase):
    def test_allows_employee_who_turns_eighteen_on_joining_date(self):
        doc = SimpleNamespace(date_of_birth=date(2008, 8, 25), date_of_joining=date(2026, 8, 25))

        with (
            patch.object(employee, "today", return_value="2026-08-25"),
            patch.object(employee.frappe, "_", side_effect=lambda message: message),
            patch.object(employee.frappe, "throw") as throw,
        ):
            employee.validate_age_at_joining(doc)

        throw.assert_not_called()

    def test_rejects_employee_below_eighteen_at_joining(self):
        doc = SimpleNamespace(date_of_birth=date(2008, 8, 26), date_of_joining=date(2026, 8, 25))

        with (
            patch.object(employee, "today", return_value="2026-08-25"),
            patch.object(employee.frappe, "_", side_effect=lambda message: message),
            patch.object(employee.frappe, "throw") as throw,
        ):
            employee.validate_age_at_joining(doc)

        throw.assert_called_once_with("Employee must be at least 18 years old on the Date of Joining.")

    def test_rejects_future_joining_date(self):
        doc = SimpleNamespace(date_of_birth=date(2000, 1, 1), date_of_joining=date(2026, 8, 26))

        with (
            patch.object(employee, "today", return_value="2026-08-25"),
            patch.object(employee.frappe, "_", side_effect=lambda message: message),
            patch.object(employee.frappe, "throw") as throw,
        ):
            employee.validate_age_at_joining(doc)

        throw.assert_called_once_with("Date of Joining cannot be greater than today.")
