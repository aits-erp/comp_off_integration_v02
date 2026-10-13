from unittest.mock import patch
from unittest import TestCase

import frappe

from real_group_hrms.doc_events.salary_structure_assignment import get_esic_exit_date_for_assignment


class TestESICExitDate(TestCase):
    def test_exit_date_set_for_10003_like_may_to_june_increment(self):
        self.assert_esic_exit_date(
            employee="ESIC-EXIT-001",
            may_basic=20975,
            june_basic=23338,
            may_esic=158,
            june_esic=0,
            expected_exit_date="2026-09-30",
        )

    def test_exit_date_set_when_june_increment_crosses_esic_limit(self):
        self.assert_esic_exit_date(
            employee="ESIC-EXIT-002",
            may_basic=18000,
            june_basic=25000,
            may_esic=135,
            june_esic=0,
            expected_exit_date="2026-09-30",
        )

    def test_exit_date_not_set_when_june_formula_deducts_at_19000_basic(self):
        self.assert_esic_exit_date(
            employee="ESIC-CONTINUE-001",
            may_basic=18000,
            june_basic=19000,
            may_esic=135,
            june_esic=143,
            expected_exit_date=None,
        )

    def test_exit_date_not_set_when_june_formula_deducts_at_limit_basic(self):
        self.assert_esic_exit_date(
            employee="ESIC-CONTINUE-002",
            may_basic=20500,
            june_basic=21000,
            may_esic=154,
            june_esic=158,
            expected_exit_date=None,
        )

    def test_exit_date_not_set_when_june_formula_deducts_for_normal_esic_employee(self):
        self.assert_esic_exit_date(
            employee="ESIC-CONTINUE-003",
            may_basic=15000,
            june_basic=16000,
            may_esic=113,
            june_esic=120,
            expected_exit_date=None,
        )

    def test_exit_date_set_when_raise_takes_effect_on_period_start_day(self):
        # Mirrors employee 10196: an annual increment effective 1 April (the
        # first day of the Apr-Sep ESIC contribution period) that crosses the
        # wage limit must still continue ESIC through the period end.
        self.assert_esic_exit_date(
            employee="ESIC-EXIT-003",
            may_basic=18289,
            june_basic=22000,
            may_esic=137,
            june_esic=0,
            expected_exit_date="2026-09-30",
            previous_from_date="2026-01-01",
            current_from_date="2026-04-01",
        )

    def assert_esic_exit_date(
        self,
        employee,
        may_basic,
        june_basic,
        may_esic,
        june_esic,
        expected_exit_date,
        previous_from_date="2026-05-01",
        current_from_date="2026-06-01",
    ):
        previous_assignment = self.get_assignment(employee, previous_from_date, may_basic, "MAY")
        current_assignment = self.get_assignment(employee, current_from_date, june_basic, "JUNE")

        with self.mock_esic_context(
            previous_assignment=previous_assignment,
            current_assignment=current_assignment,
            previous_esic=may_esic,
            current_esic=june_esic,
        ):
            exit_date = get_esic_exit_date_for_assignment(current_assignment)

        if expected_exit_date:
            self.assertEqual(str(exit_date), expected_exit_date)
        else:
            self.assertIsNone(exit_date)

    def get_assignment(self, employee, from_date, basic, suffix):
        return frappe._dict(
            {
                "name": f"{employee}-{suffix}",
                "employee": employee,
                "salary_structure": f"{employee}-STRUCTURE-{suffix}",
                "from_date": from_date,
                "custom_basic_pay": basic,
                "custom_esi_exit_date": None,
            }
        )

    def mock_esic_context(
        self,
        previous_assignment,
        current_assignment,
        previous_esic,
        current_esic,
    ):
        def get_mocked_esic_amount(doc, ignore_exit_date=False):
            if doc.name == current_assignment.name:
                return current_esic
            if doc.name == previous_assignment.name:
                return previous_esic
            return 0

        return patch.multiple(
            "real_group_hrms.doc_events.salary_structure_assignment",
            get_assignment_esic_amount=get_mocked_esic_amount,
            get_previous_submitted_assignment=lambda doc: previous_assignment,
        )
