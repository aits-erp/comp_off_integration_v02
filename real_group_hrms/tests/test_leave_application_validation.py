from datetime import date, datetime
from importlib import import_module
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

leave_application = import_module("real_group_hrms.doc_events.leave_application")


class TestLeaveApplicationValidation(TestCase):
    def test_validate_el_and_cl_allows_earned_leave_with_opposite_half_comp_off(self):
        doc = SimpleNamespace(
            leave_type="Earned Leave - Plant",
            employee="230011",
            name="LAP-NEW",
            from_date=date(2026, 3, 5),
            to_date=date(2026, 3, 5),
            half_day=1,
            half_day_date=date(2026, 3, 5),
        )
        existing = SimpleNamespace(
            name="LAP-CO",
            leave_type="Compensatory Off",
            from_date=date(2026, 3, 5),
            to_date=date(2026, 3, 5),
            half_day=1,
            half_day_date=date(2026, 3, 5),
        )

        with patch.object(leave_application.frappe, "get_all", return_value=[existing]):
            leave_application.validate_el_and_cl(doc)

    def test_validate_el_and_cl_fetches_only_relevant_opposite_boundaries(self):
        doc = SimpleNamespace(
            leave_type="Casual Leave - Plant",
            employee="230011",
            name="LAP-NEW",
            from_date=date(2026, 5, 20),
            to_date=date(2026, 5, 20),
            half_day=0,
            half_day_date=None,
            custom_half_type=None,
        )

        with patch.object(leave_application.frappe, "get_all", return_value=[]) as get_all:
            leave_application.validate_el_and_cl(doc)

        leave_filters = [
            call.kwargs["filters"]
            for call in get_all.call_args_list
            if call.args and call.args[0] == "Leave Application"
        ]
        self.assertEqual(len(leave_filters), 3)
        self.assertTrue(all(filters["leave_type"] == ["like", "%Earned%"] for filters in leave_filters))
        self.assertIn("from_date", leave_filters[0])
        self.assertIn("to_date", leave_filters[0])
        self.assertEqual(leave_filters[1]["to_date"], ["<", doc.from_date])
        self.assertEqual(leave_filters[2]["from_date"], [">", doc.to_date])

    def test_second_half_leave_allows_first_half_presence_on_boundary(self):
        earlier = SimpleNamespace(
            leave_type="Earned Leave - Plant",
            from_date=date(2026, 5, 1),
            to_date=date(2026, 5, 1),
            half_day=0,
            half_day_date=None,
            custom_half_type=None,
        )
        later = SimpleNamespace(
            leave_type="Casual Leave - Plant",
            from_date=date(2026, 5, 3),
            to_date=date(2026, 5, 3),
            half_day=1,
            half_day_date=date(2026, 5, 3),
            custom_half_type="Second Half",
        )

        def has_separator(employee, separator_date, required_half=None):
            return separator_date == date(2026, 5, 3) and required_half == "First Half"

        with patch.object(
            leave_application,
            "has_present_or_approved_request",
            side_effect=has_separator,
        ):
            self.assertTrue(leave_application.has_valid_el_cl_separator("230011", earlier, later))

    def test_first_half_leave_rejects_second_half_presence_on_boundary(self):
        earlier = SimpleNamespace(
            leave_type="Earned Leave - Plant",
            from_date=date(2026, 5, 1),
            to_date=date(2026, 5, 1),
            half_day=0,
            half_day_date=None,
            custom_half_type=None,
        )
        later = SimpleNamespace(
            leave_type="Casual Leave - Plant",
            from_date=date(2026, 5, 3),
            to_date=date(2026, 5, 3),
            half_day=1,
            half_day_date=date(2026, 5, 3),
            custom_half_type="First Half",
        )

        def has_separator(employee, separator_date, required_half=None):
            return separator_date == date(2026, 5, 3) and required_half == "Second Half"

        with patch.object(
            leave_application,
            "has_present_or_approved_request",
            side_effect=has_separator,
        ):
            self.assertFalse(leave_application.has_valid_el_cl_separator("230011", earlier, later))

    def test_infers_second_half_presence_from_attendance_times(self):
        attendance = SimpleNamespace(
            shift="G",
            attendance_date=date(2026, 5, 6),
            in_time=datetime(2026, 5, 6, 13, 35, 40),
            out_time=datetime(2026, 5, 6, 18, 0, 57),
        )
        shift = SimpleNamespace(start_time="9:00:00", end_time="18:00:00")

        frappe_db = SimpleNamespace(get_value=lambda *args, **kwargs: shift)
        with patch.object(leave_application.frappe, "db", frappe_db):
            self.assertEqual(
                leave_application.infer_present_half_from_attendance(attendance),
                "Second Half",
            )

    def test_present_attendance_without_evidence_is_not_a_valid_separator(self):
        attendance = SimpleNamespace(
            status="Present",
            custom_half_type=None,
            leave_application=None,
            attendance_request=None,
            shift=None,
            attendance_date=date(2026, 5, 10),
            in_time=None,
            out_time=None,
            custom_attendance_tag="WO",
        )

        with patch.object(leave_application.frappe, "get_all", return_value=[attendance]):
            self.assertFalse(leave_application.has_present_attendance("12654", date(2026, 5, 10)))

    def test_present_attendance_with_checkin_evidence_is_a_valid_separator(self):
        attendance = SimpleNamespace(
            status="Present",
            custom_half_type=None,
            leave_application=None,
            attendance_request=None,
            shift="G",
            attendance_date=date(2026, 5, 12),
            in_time=datetime(2026, 5, 12, 9, 1, 0),
            out_time=datetime(2026, 5, 12, 18, 3, 0),
            custom_attendance_tag=None,
        )

        with patch.object(leave_application.frappe, "get_all", return_value=[attendance]):
            self.assertTrue(leave_application.has_present_attendance("12654", date(2026, 5, 12)))

    def test_present_attendance_with_attendance_request_is_a_valid_separator(self):
        attendance = SimpleNamespace(
            status="Present",
            custom_half_type=None,
            leave_application=None,
            attendance_request="HR-ARQ-26-05-00089",
            shift=None,
            attendance_date=date(2026, 5, 15),
            in_time=None,
            out_time=None,
            custom_attendance_tag=None,
        )

        with patch.object(leave_application.frappe, "get_all", return_value=[attendance]):
            self.assertTrue(leave_application.has_present_attendance("12654", date(2026, 5, 15)))

    def test_present_attendance_with_no_punch_tag_is_a_valid_separator(self):
        attendance = SimpleNamespace(
            status="Present",
            custom_half_type=None,
            leave_application=None,
            attendance_request=None,
            shift=None,
            attendance_date=date(2026, 5, 5),
            in_time=None,
            out_time=None,
            custom_attendance_tag="P",
        )

        with patch.object(leave_application.frappe, "get_all", return_value=[attendance]):
            self.assertTrue(leave_application.has_present_attendance("10085", date(2026, 5, 5)))

    def test_present_attendance_with_wo_tag_is_not_a_valid_separator(self):
        attendance = SimpleNamespace(
            status="Present",
            custom_half_type=None,
            leave_application=None,
            attendance_request=None,
            shift=None,
            attendance_date=date(2026, 5, 3),
            in_time=None,
            out_time=None,
            custom_attendance_tag="WO",
        )

        with patch.object(leave_application.frappe, "get_all", return_value=[attendance]):
            self.assertFalse(leave_application.has_present_attendance("10085", date(2026, 5, 3)))

    def test_validate_el_and_cl_allows_casual_leave_with_opposite_half_lwp(self):
        doc = SimpleNamespace(
            leave_type="Casual Leave - Plant",
            employee="230011",
            name="LAP-NEW",
            from_date=date(2026, 3, 5),
            to_date=date(2026, 3, 5),
            half_day=1,
            half_day_date=date(2026, 3, 5),
        )
        existing = SimpleNamespace(
            name="LAP-LWP",
            leave_type="Leave Without Pay",
            from_date=date(2026, 3, 5),
            to_date=date(2026, 3, 5),
            half_day=1,
            half_day_date=date(2026, 3, 5),
        )

        with patch.object(leave_application.frappe, "get_all", return_value=[existing]):
            leave_application.validate_el_and_cl(doc)
