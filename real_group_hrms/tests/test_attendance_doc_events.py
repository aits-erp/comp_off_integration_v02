from datetime import timedelta
from datetime import date
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, call, patch

from real_group_hrms.doc_events import attendance as attendance_doc_events
from real_group_hrms.doc_events.attendance import validate
from real_group_hrms.overrides import leave_application as leave_application_override
from real_group_hrms.real_group.doctype.reprocess_attendance import (
    reprocess_attendance as reprocess_attendance_doctype,
)


class TestAttendanceDocEvents(TestCase):
    def test_validate_keeps_sub_day_custom_working_hours(self):
        doc = SimpleNamespace(working_hours=8.5, custom_working_hours=None)

        validate(doc)

        self.assertEqual(doc.custom_working_hours, timedelta(hours=8, minutes=30))

    def test_validate_skips_custom_working_hours_for_24h_plus(self):
        doc = SimpleNamespace(working_hours=24.02, custom_working_hours=None)

        validate(doc)

        self.assertIsNone(doc.custom_working_hours)

    def test_has_valid_holiday_in_out_pair_uses_same_day_unlinked_checkins(self):
        doc = SimpleNamespace(
            name="HR-ATT-TEST-1", employee="10794", attendance_date=date(2026, 2, 16)
        )

        with patch.object(
            attendance_doc_events.frappe,
            "get_all",
            side_effect=[[], ["IN", "OUT"]],
        ):
            self.assertTrue(attendance_doc_events.has_valid_holiday_in_out_pair(doc))


class TestCrossDayIncentiveReplacement(TestCase):
    def _doc(self):
        return SimpleNamespace(
            name="HR-ATT-TEST-1", employee="10399", attendance_date=date(2026, 7, 30)
        )

    def test_regular_shift_does_not_use_cross_day_replacement(self):
        doc = self._doc()
        with (
            patch.object(attendance_doc_events.frappe, "get_all", return_value=["G"]),
            patch.object(
                attendance_doc_events.frappe, "get_cached_value", return_value=0
            ),
        ):
            action, logs = (
                attendance_doc_events.get_cross_day_incentive_replacement_action(
                    doc, 0.5
                )
            )

        self.assertIsNone(action)
        self.assertEqual(logs, [])

    def test_cross_day_completion_replaces_lower_credit_for_same_work_date(self):
        doc = self._doc()
        existing_log = {"name": "INC-0001", "credit": 0.5}
        with (
            patch.object(
                attendance_doc_events.frappe,
                "get_all",
                side_effect=[["G", "7"], [existing_log]],
            ),
            patch.object(
                attendance_doc_events.frappe,
                "get_cached_value",
                side_effect=lambda doctype, name, field: name == "7",
            ),
        ):
            action, logs = (
                attendance_doc_events.get_cross_day_incentive_replacement_action(
                    doc, 1.5
                )
            )

        self.assertEqual(action, "replace")
        self.assertEqual(logs, [existing_log])

    def test_cross_day_repeat_does_not_replace_equal_credit(self):
        doc = self._doc()
        existing_log = {"name": "INC-0002", "credit": 1.5}
        with (
            patch.object(
                attendance_doc_events.frappe,
                "get_all",
                side_effect=[["G", "7"], [existing_log]],
            ),
            patch.object(
                attendance_doc_events.frappe,
                "get_cached_value",
                side_effect=lambda doctype, name, field: name == "7",
            ),
        ):
            action, logs = (
                attendance_doc_events.get_cross_day_incentive_replacement_action(
                    doc, 1.5
                )
            )

        self.assertEqual(action, "skip")
        self.assertEqual(logs, [existing_log])

    def test_replacement_cancels_additional_salary_before_old_incentive_log(self):
        doc = SimpleNamespace(
            name="HR-ATT-TEST-1",
            employee="10399",
            attendance_date=date(2026, 7, 30),
            working_hours=24.27,
            shift="G",
        )
        employee = SimpleNamespace(name="10399", date_of_joining=None, grade="E2", branch="Plant Site")
        grade = SimpleNamespace(
            custom_present_on_holiday=None,
            custom_extra_work_hour="Incentive",
            custom_incentive_ceiling=3500,
        )
        shift = SimpleNamespace(custom_shift_time="9:00:00")
        matrix = SimpleNamespace(
            items=[
                SimpleNamespace(
                    from_hrs=timedelta(hours=11),
                    to_hrs=timedelta(hours=16),
                    c_off_credit=1.5,
                )
            ]
        )
        old_additional_salary = Mock(name="old_additional_salary")
        old_incentive_log = Mock(name="old_incentive_log")
        fresh_incentive_log = Mock(name="fresh_incentive_log")
        fresh_incentive_log.name = "INC-NEW"
        fresh_additional_salary = Mock(name="fresh_additional_salary")
        fake_frappe = SimpleNamespace(
            db=SimpleNamespace(
                exists=Mock(side_effect=[True, "Plant Site-09:00:00"]),
                get_value=Mock(side_effect=["HR-ADS-TEST-1", "10399", 23500]),
                get_all=Mock(return_value=[]),
                savepoint=Mock(),
                rollback=Mock(),
            ),
            get_cached_doc=Mock(side_effect=[employee, grade, shift, matrix]),
            get_doc=Mock(
                side_effect=[
                    old_additional_salary,
                    old_incentive_log,
                    fresh_incentive_log,
                    fresh_additional_salary,
                ]
            ),
        )

        with (
            patch.object(attendance_doc_events, "frappe", fake_frappe),
            patch.object(attendance_doc_events, "get_reprocess_reference", return_value=None),
            patch.object(attendance_doc_events, "is_holiday_for_employee", return_value=None),
            patch.object(
                attendance_doc_events,
                "get_cross_day_incentive_replacement_action",
                return_value=("replace", [SimpleNamespace(name="INC-OLD")]),
            ),
        ):
            attendance_doc_events.allocate_incentive(doc)

        self.assertEqual(
            fake_frappe.get_doc.call_args_list[:2],
            [call("Additional Salary", "HR-ADS-TEST-1"), call("Incentive Log", "INC-OLD")],
        )
        old_additional_salary.cancel.assert_called_once_with()
        old_additional_salary.delete.assert_called_once_with()
        old_incentive_log.cancel.assert_called_once_with()
        fresh_incentive_log.insert.assert_called_once_with(ignore_permissions=True)
        fresh_incentive_log.submit.assert_called_once_with()
        fresh_additional_salary.insert.assert_called_once_with(ignore_permissions=True)
        fresh_additional_salary.submit.assert_called_once_with()


class TestLeaveApplicationIncentiveSuppression(TestCase):
    def _doc(self, leave_application=None):
        return SimpleNamespace(
            employee="80495",
            attendance_date=date(2026, 7, 7),
            status="Present",
            leave_application=leave_application,
            attendance_request=None,
            custom_marked_absent_by_sandwich=False,
        )

    def test_leave_linked_attendance_does_not_queue_an_incentive(self):
        doc = self._doc(leave_application="RI-LAP-24-0000037")

        with (
            patch.object(attendance_doc_events, "update_attendance_status"),
            patch.object(attendance_doc_events, "update_attendance_tag"),
            patch.object(attendance_doc_events.frappe, "enqueue") as enqueue,
            patch.object(
                attendance_doc_events.frappe,
                "flags",
                attendance_doc_events.frappe._dict(in_reprocess_attendance=False),
            ),
        ):
            attendance_doc_events.on_submit(doc)

        self.assertNotIn(
            call(
                attendance_doc_events.allocate_incentive,
                doc=doc,
                queue="long",
                enqueue_after_commit=True,
            ),
            enqueue.call_args_list,
        )

    def test_leave_approval_update_does_not_queue_an_incentive(self):
        doc = self._doc(leave_application="RI-LAP-24-0000037")

        with patch.object(leave_application_override.frappe, "enqueue") as enqueue:
            leave_application_override.LeaveApplicationOverride.process_jobs_after_update(
                None, doc
            )

        self.assertEqual(enqueue.call_count, 2)
        self.assertIn(
            call(
                leave_application_override.allocate_c_off,
                doc=doc,
                queue="long",
                enqueue_after_commit=True,
            ),
            enqueue.call_args_list,
        )
        self.assertIn(
            call(
                attendance_doc_events.allocate_c_off,
                doc=doc,
                queue="long",
                enqueue_after_commit=True,
            ),
            enqueue.call_args_list,
        )

    def test_direct_attendance_still_queues_an_incentive(self):
        doc = self._doc()

        with (
            patch.object(attendance_doc_events, "update_attendance_status"),
            patch.object(attendance_doc_events, "update_attendance_tag"),
            patch.object(attendance_doc_events.frappe, "enqueue") as enqueue,
            patch.object(
                attendance_doc_events.frappe,
                "flags",
                attendance_doc_events.frappe._dict(in_reprocess_attendance=False),
            ),
        ):
            attendance_doc_events.on_submit(doc)

        self.assertIn(
            call(
                attendance_doc_events.allocate_incentive,
                doc=doc,
                queue="long",
                enqueue_after_commit=True,
            ),
            enqueue.call_args_list,
        )

    def test_leave_cancellation_keeps_existing_incentive_logs(self):
        doc = self._doc(leave_application="RI-LAP-24-0000037")

        with (
            patch.object(
                attendance_doc_events, "cancel_incentive_or_c_off"
            ) as cancel_incentive_or_c_off,
            patch.object(
                attendance_doc_events.frappe,
                "flags",
                attendance_doc_events.frappe._dict(
                    in_leave_application_attendance_sync=True
                ),
            ),
        ):
            attendance_doc_events.on_cancel(doc)

        cancel_incentive_or_c_off.assert_called_once_with(doc, cancel_incentive=False)

    def test_direct_attendance_cancellation_still_reverses_its_incentive(self):
        doc = self._doc()

        with (
            patch.object(
                attendance_doc_events, "cancel_incentive_or_c_off"
            ) as cancel_incentive_or_c_off,
            patch.object(
                attendance_doc_events.frappe,
                "flags",
                attendance_doc_events.frappe._dict(
                    in_leave_application_attendance_sync=False
                ),
            ),
        ):
            attendance_doc_events.on_cancel(doc)

        cancel_incentive_or_c_off.assert_called_once_with(doc, cancel_incentive=True)


class TestReprocessLeaveIncentiveSuppression(TestCase):
    def _run_reprocess_post_processing(self, leave_application=None):
        attendance = SimpleNamespace(
            name="HR-ATT-TEST-1",
            status="On Leave" if leave_application else "Present",
            leave_application=leave_application,
            attendance_request=None,
        )
        reprocess = SimpleNamespace(
            employee="80495",
            name="HR-RPA-TEST-1",
            apply_attendance_requests=lambda: None,
            apply_leave_applications=lambda: None,
        )

        with (
            patch.object(
                reprocess_attendance_doctype.frappe,
                "get_all",
                return_value=[attendance.name],
            ),
            patch.object(
                reprocess_attendance_doctype.frappe,
                "get_doc",
                return_value=attendance,
            ),
            patch.object(reprocess_attendance_doctype, "allocate_c_off") as allocate_c_off,
            patch.object(
                reprocess_attendance_doctype, "allocate_incentive"
            ) as allocate_incentive,
            patch.object(reprocess_attendance_doctype, "sandwich_attendance"),
            patch.object(reprocess_attendance_doctype, "revert_sandwich_attendance"),
        ):
            reprocess_attendance_doctype.ReprocessAttendance.process_leave_and_requests(
                reprocess, "2026-07-07", "2026-07-07"
            )

        return attendance, allocate_c_off, allocate_incentive

    def test_leave_linked_attendance_does_not_get_reprocess_incentive(self):
        attendance, allocate_c_off, allocate_incentive = (
            self._run_reprocess_post_processing("RI-LAP-24-0000038")
        )

        allocate_c_off.assert_called_once_with(attendance)
        allocate_incentive.assert_not_called()

    def test_regular_attendance_still_gets_reprocess_incentive(self):
        attendance, _, allocate_incentive = self._run_reprocess_post_processing()

        allocate_incentive.assert_called_once_with(attendance)


class TestUnboundedSandwichSearchStaysRemoved(TestCase):
    """Regression guard: the unbounded historical 'nearest present' search
    (real_group/doc_events/attendance.py, removed 2026-07) must never come
    back. It caused sandwich corrections to reach back months (seen live
    reaching to Aug-2025 data) and to fire non-deterministically, days late."""

    def test_get_mark_to_absent_is_gone(self):
        self.assertFalse(hasattr(attendance_doc_events, "get_mark_to_absent"))

    def test_is_sandwich_boundary_status_is_gone(self):
        self.assertFalse(hasattr(attendance_doc_events, "is_sandwich_boundary_status"))


class TestIsSandwichAbsenceSide(TestCase):
    def _att(self, status, leave_application=None, attendance_request=None):
        return attendance_doc_events.frappe._dict(
            status=status,
            leave_application=leave_application,
            attendance_request=attendance_request,
        )

    def test_no_attendance_record_is_not_absence_side(self):
        with patch.object(
            attendance_doc_events.frappe.db, "get_value", return_value=None
        ):
            self.assertFalse(
                attendance_doc_events.is_sandwich_absence_side(
                    "12201", date(2026, 6, 24)
                )
            )

    def test_absent_is_absence_side(self):
        with patch.object(
            attendance_doc_events.frappe.db,
            "get_value",
            return_value=self._att("Absent"),
        ):
            self.assertTrue(
                attendance_doc_events.is_sandwich_absence_side(
                    "12201", date(2026, 6, 24)
                )
            )

    def test_on_leave_is_absence_side(self):
        with patch.object(
            attendance_doc_events.frappe.db,
            "get_value",
            return_value=self._att("On Leave"),
        ):
            self.assertTrue(
                attendance_doc_events.is_sandwich_absence_side(
                    "12201", date(2026, 6, 24)
                )
            )

    def test_full_day_present_is_not_absence_side(self):
        with patch.object(
            attendance_doc_events.frappe.db,
            "get_value",
            return_value=self._att("Present"),
        ):
            self.assertFalse(
                attendance_doc_events.is_sandwich_absence_side(
                    "12201", date(2026, 6, 24)
                )
            )

    def test_physical_half_day_is_not_absence_side(self):
        with patch.object(
            attendance_doc_events.frappe.db,
            "get_value",
            return_value=self._att("Half Day"),
        ):
            self.assertFalse(
                attendance_doc_events.is_sandwich_absence_side(
                    "12201", date(2026, 6, 24)
                )
            )

    def test_half_day_via_attendance_request_is_not_absence_side(self):
        att = self._att("Half Day", attendance_request="AR-1")
        with patch.object(
            attendance_doc_events.frappe.db, "get_value", return_value=att
        ):
            self.assertFalse(
                attendance_doc_events.is_sandwich_absence_side(
                    "12201", date(2026, 6, 24)
                )
            )

    def test_half_day_via_leave_application_is_absence_side(self):
        att = self._att("Half Day", leave_application="LA-1")
        with patch.object(
            attendance_doc_events.frappe.db, "get_value", return_value=att
        ):
            self.assertTrue(
                attendance_doc_events.is_sandwich_absence_side(
                    "12201", date(2026, 6, 24)
                )
            )

    def test_full_day_attendance_request_wins_over_leave_application(self):
        att = self._att("Half Day", leave_application="LA-1", attendance_request="AR-1")
        with patch.object(
            attendance_doc_events.frappe.db, "get_value", return_value=att
        ):
            self.assertFalse(
                attendance_doc_events.is_sandwich_absence_side(
                    "12201", date(2026, 6, 24)
                )
            )


class TestGetHolidayBlock(TestCase):
    def test_returns_none_when_date_is_not_a_holiday(self):
        with (
            patch.object(
                attendance_doc_events, "should_consider_holiday", return_value=False
            ),
            patch.object(
                attendance_doc_events, "get_weekly_off_based_on_date", return_value=None
            ),
        ):
            block = attendance_doc_events.get_holiday_block("12201", date(2026, 6, 26))
        self.assertIsNone(block)

    def test_single_day_block(self):
        holiday_dates = {date(2026, 6, 25)}
        with (
            patch.object(
                attendance_doc_events,
                "should_consider_holiday",
                side_effect=lambda employee, d, weekly_off_name=None: d
                in holiday_dates,
            ),
            patch.object(
                attendance_doc_events,
                "get_weekly_off_based_on_date",
                return_value="Thursday",
            ),
        ):
            block = attendance_doc_events.get_holiday_block("12201", date(2026, 6, 25))
        self.assertEqual(block, (date(2026, 6, 25), date(2026, 6, 25)))

    def test_multi_day_block_is_bounded_to_contiguous_holidays(self):
        holiday_dates = {date(2026, 6, 24), date(2026, 6, 25), date(2026, 6, 26)}
        with (
            patch.object(
                attendance_doc_events,
                "should_consider_holiday",
                side_effect=lambda employee, d, weekly_off_name=None: d
                in holiday_dates,
            ),
            patch.object(
                attendance_doc_events,
                "get_weekly_off_based_on_date",
                return_value="Thursday",
            ),
        ):
            block = attendance_doc_events.get_holiday_block("12201", date(2026, 6, 25))
        self.assertEqual(block, (date(2026, 6, 24), date(2026, 6, 26)))


class TestSandwichAttendance(TestCase):
    def _doc(self, employee="12201", attendance_date=date(2026, 6, 26)):
        return SimpleNamespace(
            employee=employee, attendance_date=attendance_date, status="Absent"
        )

    def test_marks_single_day_block_when_both_boundaries_are_absence_side(self):
        doc = self._doc()
        with (
            patch.object(attendance_doc_events.frappe, "get_value", return_value="E4"),
            patch.object(attendance_doc_events.frappe.db, "get_value", return_value=1),
            patch.object(
                attendance_doc_events, "is_sandwich_absence_side", return_value=True
            ),
            patch.object(
                attendance_doc_events,
                "get_holiday_block",
                return_value=(date(2026, 6, 25), date(2026, 6, 25)),
            ),
            patch.object(
                attendance_doc_events, "_mark_date_absent_by_sandwich"
            ) as mock_mark,
        ):
            attendance_doc_events.sandwich_attendance(doc)
        mock_mark.assert_called_once_with("12201", date(2026, 6, 25))

    def test_marks_every_date_in_a_multi_day_block(self):
        doc = self._doc()
        with (
            patch.object(attendance_doc_events.frappe, "get_value", return_value="E4"),
            patch.object(attendance_doc_events.frappe.db, "get_value", return_value=1),
            patch.object(
                attendance_doc_events, "is_sandwich_absence_side", return_value=True
            ),
            patch.object(
                attendance_doc_events,
                "get_holiday_block",
                return_value=(date(2026, 6, 24), date(2026, 6, 26)),
            ),
            patch.object(
                attendance_doc_events, "_mark_date_absent_by_sandwich"
            ) as mock_mark,
        ):
            attendance_doc_events.sandwich_attendance(doc)
        self.assertEqual(
            mock_mark.call_args_list,
            [
                call("12201", date(2026, 6, 24)),
                call("12201", date(2026, 6, 25)),
                call("12201", date(2026, 6, 26)),
            ],
        )

    def test_does_not_mark_when_no_adjacent_holiday_block(self):
        doc = self._doc()
        with (
            patch.object(attendance_doc_events.frappe, "get_value", return_value="E4"),
            patch.object(attendance_doc_events.frappe.db, "get_value", return_value=1),
            patch.object(
                attendance_doc_events, "is_sandwich_absence_side", return_value=True
            ),
            patch.object(attendance_doc_events, "get_holiday_block", return_value=None),
            patch.object(
                attendance_doc_events, "_mark_date_absent_by_sandwich"
            ) as mock_mark,
        ):
            attendance_doc_events.sandwich_attendance(doc)
        mock_mark.assert_not_called()

    def test_does_not_mark_when_day_before_block_is_presence_side(self):
        doc = self._doc()
        with (
            patch.object(attendance_doc_events.frappe, "get_value", return_value="E4"),
            patch.object(attendance_doc_events.frappe.db, "get_value", return_value=1),
            patch.object(
                attendance_doc_events,
                "is_sandwich_absence_side",
                side_effect=[True, False],
            ),
            patch.object(
                attendance_doc_events,
                "get_holiday_block",
                return_value=(date(2026, 6, 25), date(2026, 6, 25)),
            ),
            patch.object(
                attendance_doc_events, "_mark_date_absent_by_sandwich"
            ) as mock_mark,
        ):
            attendance_doc_events.sandwich_attendance(doc)
        mock_mark.assert_not_called()

    def test_grade_flag_disabled_skips_entirely(self):
        doc = self._doc()
        with (
            patch.object(attendance_doc_events.frappe, "get_value", return_value="E4"),
            patch.object(attendance_doc_events.frappe.db, "get_value", return_value=0),
            patch.object(attendance_doc_events, "get_holiday_block") as mock_block,
        ):
            attendance_doc_events.sandwich_attendance(doc)
        mock_block.assert_not_called()

    def test_no_grade_skips_entirely(self):
        doc = self._doc()
        with (
            patch.object(attendance_doc_events.frappe, "get_value", return_value=None),
            patch.object(attendance_doc_events, "get_holiday_block") as mock_block,
        ):
            attendance_doc_events.sandwich_attendance(doc)
        mock_block.assert_not_called()


class TestRevertSandwichAttendance(TestCase):
    def _doc(
        self, employee="12201", attendance_date=date(2026, 6, 26), status="Present"
    ):
        return SimpleNamespace(
            employee=employee, attendance_date=attendance_date, status=status
        )

    def test_reverts_holiday_blocks_on_both_sides(self):
        doc = self._doc()

        def fake_block(employee, d):
            if d == date(2026, 6, 25):
                return (date(2026, 6, 25), date(2026, 6, 25))
            if d == date(2026, 6, 27):
                return (date(2026, 6, 27), date(2026, 6, 27))
            return None

        with (
            patch.object(attendance_doc_events.frappe, "get_value", return_value="E4"),
            patch.object(attendance_doc_events.frappe.db, "get_value", return_value=1),
            patch.object(
                attendance_doc_events, "is_sandwich_absence_side", return_value=False
            ),
            patch.object(
                attendance_doc_events, "get_holiday_block", side_effect=fake_block
            ),
            patch.object(
                attendance_doc_events, "_revert_sandwich_block"
            ) as mock_revert,
        ):
            attendance_doc_events.revert_sandwich_attendance(doc)
        self.assertEqual(
            mock_revert.call_args_list,
            [
                call("12201", date(2026, 6, 25), date(2026, 6, 25)),
                call("12201", date(2026, 6, 27), date(2026, 6, 27)),
            ],
        )

    def test_no_op_when_date_is_still_absence_side(self):
        # e.g. a Half Day driven by an approved Leave Application - still
        # counts as the absence side, so an already-sandwiched neighbor
        # must not be reverted just because this record got resubmitted.
        doc = self._doc(status="Half Day")
        with (
            patch.object(attendance_doc_events.frappe, "get_value", return_value="E4"),
            patch.object(attendance_doc_events.frappe.db, "get_value", return_value=1),
            patch.object(
                attendance_doc_events, "is_sandwich_absence_side", return_value=True
            ),
            patch.object(attendance_doc_events, "get_holiday_block") as mock_block,
            patch.object(
                attendance_doc_events, "_revert_sandwich_block"
            ) as mock_revert,
        ):
            attendance_doc_events.revert_sandwich_attendance(doc)
        mock_block.assert_not_called()
        mock_revert.assert_not_called()


class TestMarkDateAbsentBySandwich(TestCase):
    def test_exception_is_caught_and_logged_not_raised(self):
        with (
            patch.object(
                attendance_doc_events.frappe.db, "exists", side_effect=Exception("boom")
            ),
            patch.object(attendance_doc_events.frappe, "log_error") as mock_log,
        ):
            attendance_doc_events._mark_date_absent_by_sandwich(
                "12201", date(2026, 6, 25)
            )
        mock_log.assert_called_once()


# ---------------------------------------------------------------------------
# Single-record combination matrix (mock characterization).
#
# These lock in the CURRENT behaviour of the two doc-event deciders for the
# single-item-per-day scenarios (one leave OR one attendance request OR plain
# checkin presence), across the three day contexts the business cares about:
# a normal working day, a full Weekly Off, and a full Holiday.
#
#   * update_attendance_tag()  -> custom_attendance_tag
#   * is_sandwich_absence_side() -> whether the day counts as "absence side"
#     for the sandwich policy
#
# Expected values were captured by running the real functions (characterization,
# not a hand-written spec) so they act as a regression baseline. Multi-record
# combinations (two half-day items on one date) are covered by the integration
# tests in TestSandwichCombinationIntegration instead, because their runtime
# resolution cannot be faithfully reproduced with mocks.
#
# Leave-type / attendance-request vocabulary used by the matrix:
#   EL = Earned Leave, CL = Casual Leave, CO = Compensatory Off,
#   LWP = Leave Without Pay (is_lwp), OD = Attendance Request reason "Official",
#   Mis Punch = Attendance Request reason "Mis Punch".
# ---------------------------------------------------------------------------

_LEAVE_TYPES = {
    "EL": SimpleNamespace(name="Earned Leave - Plant", is_lwp=0, is_compensatory=0),
    "CL": SimpleNamespace(name="Casual Leave - Plant", is_lwp=0, is_compensatory=0),
    "CO": SimpleNamespace(name="Compensatory Off", is_lwp=0, is_compensatory=1),
    "LWP": SimpleNamespace(name="Leave Without Pay", is_lwp=1, is_compensatory=0),
}

_DAY_CONTEXTS = {
    "working": False,
    "weekly_off": {
        "is_holiday": True,
        "is_weekly_off": True,
        "is_half_day": False,
        "half_type": None,
        "holiday_name": "WO",
    },
    "holiday": {
        "is_holiday": True,
        "is_weekly_off": False,
        "is_half_day": False,
        "half_type": None,
        "holiday_name": "HO",
    },
}

# label -> (doc state, {context: expected_tag}, expected_absence_side)
_SINGLE_RECORD_MATRIX = [
    (
        "full_present",
        dict(status="Present", leave=None, ar=None, in_out=True),
        {"working": "P", "weekly_off": "POW", "holiday": "POH"},
        False,
    ),
    (
        "half_present",
        dict(status="Half Day", leave=None, ar=None, in_out=False),
        {"working": "HD", "weekly_off": "WO", "holiday": "HO"},
        False,
    ),
    (
        "full_od",
        dict(status="Present", leave=None, ar="Official", in_out=False),
        {"working": "P", "weekly_off": "WO", "holiday": "HO"},
        False,
    ),
    (
        "half_od",
        dict(status="Half Day", leave=None, ar="Official", in_out=False),
        {"working": "HD", "weekly_off": "WO", "holiday": "HO"},
        False,
    ),
    (
        "full_el",
        dict(status="On Leave", leave="EL", ar=None, in_out=False),
        {"working": "EL", "weekly_off": "EL", "holiday": "EL"},
        True,
    ),
    (
        "full_cl",
        dict(status="On Leave", leave="CL", ar=None, in_out=False),
        {"working": "CL", "weekly_off": "CL", "holiday": "CL"},
        True,
    ),
    (
        "full_co",
        dict(status="On Leave", leave="CO", ar=None, in_out=False),
        {"working": "CO", "weekly_off": "CO", "holiday": "CO"},
        True,
    ),
    (
        "full_lwp",
        dict(status="On Leave", leave="LWP", ar=None, in_out=False),
        {"working": "LWP", "weekly_off": "A", "holiday": "A"},
        True,
    ),
    (
        "full_mispunch",
        dict(status="Half Day", leave=None, ar="Mis Punch", in_out=False),
        {"working": "HD", "weekly_off": "WO", "holiday": "HO"},
        False,
    ),
    (
        "half_mispunch",
        dict(status="Half Day", leave=None, ar="Mis Punch", in_out=False),
        {"working": "HD", "weekly_off": "WO", "holiday": "HO"},
        False,
    ),
]


def _run_update_attendance_tag(scenario, context):
    """Drive the real update_attendance_tag() with the data-access boundary
    mocked, returning the tag it writes."""
    A = attendance_doc_events
    captured = {}
    doc = SimpleNamespace(
        name="ATT-TEST",
        employee="EMP",
        attendance_date="2026-06-25",
        status=scenario["status"],
        leave_application=("LA-1" if scenario["leave"] else None),
        leave_type=(
            _LEAVE_TYPES[scenario["leave"]].name if scenario["leave"] else None
        ),
        attendance_request=("AR-1" if scenario["ar"] else None),
    )

    def gv(dt, name, field, *a, **k):
        return "E4" if dt == "Employee" else None

    def dbgv(dt, name, field=None, *a, **k):
        return 1 if dt == "Employee Grade" else None

    def getdoc(dt, name, *a, **k):
        if dt == "Leave Type":
            return _LEAVE_TYPES[scenario["leave"]]
        raise AssertionError("unexpected get_doc: " + dt)

    with (
        patch.object(A, "is_holiday_for_employee", return_value=_DAY_CONTEXTS[context]),
        patch.object(A.frappe, "get_value", side_effect=gv),
        patch.object(A.frappe.db, "get_value", side_effect=dbgv),
        patch.object(A.frappe, "get_doc", side_effect=getdoc),
        patch.object(
            A, "has_valid_holiday_in_out_pair", return_value=scenario["in_out"]
        ),
        patch.object(
            A.frappe.db,
            "set_value",
            side_effect=lambda dt, n, f, v: captured.__setitem__(f, v),
        ),
    ):
        A.update_attendance_tag(doc)
    return captured.get("custom_attendance_tag")


def _run_is_sandwich_absence_side(scenario):
    A = attendance_doc_events
    att = A.frappe._dict(
        status=scenario["status"],
        leave_application=("LA-1" if scenario["leave"] else None),
        attendance_request=("AR-1" if scenario["ar"] else None),
    )
    with patch.object(A.frappe.db, "get_value", return_value=att):
        return A.is_sandwich_absence_side("EMP", "2026-06-25")


class TestSingleRecordTagMatrix(TestCase):
    def test_tag_per_scenario_and_day_context(self):
        for label, scenario, expected_tags, _ in _SINGLE_RECORD_MATRIX:
            for context, expected_tag in expected_tags.items():
                with self.subTest(scenario=label, day=context):
                    self.assertEqual(
                        _run_update_attendance_tag(scenario, context), expected_tag
                    )

    def test_absence_side_per_scenario(self):
        for label, scenario, _, expected_absence_side in _SINGLE_RECORD_MATRIX:
            with self.subTest(scenario=label):
                self.assertEqual(
                    _run_is_sandwich_absence_side(scenario), expected_absence_side
                )


# ---------------------------------------------------------------------------
# Multi-record combination matrix (two half-day items on one date).
#
# At runtime the pipeline resolves two same-day items (leave + attendance
# request, two leaves, presence + leave, etc.) into a SINGLE Attendance record
# with one status and one primary linked leave/request. These tests characterise
# update_attendance_tag() / is_sandwich_absence_side() over that *resolved*
# doc-state.
#
# Basis of the resolved doc-state for each family (the `resolved` tuple:
# status, primary-leave-code, attendance-request-reason, has-checkin-pair):
#   * OBSERVED  - confirmed against production data:
#       - leave + attendance-request -> status Present, tag = leave code
#         (LWP stays Half Day / tag LWP);
#       - any leave-linked day -> tag = that leave's code (EL/CL/CO/LWP),
#         regardless of the resolved status.
#   * MODELLED  - inferred from update_attendance_status() where production had
#     no direct sample: two-leave days (e.g. Half EL + Half CL -> full leave,
#     primary = the first-named leave), LWP mixes, and two-attendance-request
#     days (OD/Tour/Mis Punch pairs -> Present). These rows assert the modelled
#     resolution and are the ones to review if the resolution rule changes.
#
# Note: because the three day contexts here are FULL working/weekly-off/holiday
# days (never a half-day holiday), the tag is driven by the resolved
# (status, leave, checkin) triple; the half-day-holiday combo tags
# (ELHO/ODHO/HHO/...) are a separate dimension not covered by this matrix.
# ---------------------------------------------------------------------------


def _sc(status, leave, ar, in_out):
    return dict(status=status, leave=leave, ar=ar, in_out=in_out)


# label -> (resolved scenario, {context: expected_tag}, expected_absence_side)
_MULTI_RECORD_MATRIX = [
    # Half Day Present + Half Day X
    (
        "hp_od",
        _sc("Present", None, "Official", True),
        {"working": "P", "weekly_off": "POW", "holiday": "POH"},
        False,
    ),
    (
        "hp_el",
        _sc("Present", "EL", None, True),
        {"working": "EL", "weekly_off": "EL", "holiday": "EL"},
        False,
    ),
    (
        "hp_cl",
        _sc("Present", "CL", None, True),
        {"working": "CL", "weekly_off": "CL", "holiday": "CL"},
        False,
    ),
    (
        "hp_co",
        _sc("Present", "CO", None, True),
        {"working": "CO", "weekly_off": "CO", "holiday": "CO"},
        False,
    ),
    (
        "hp_lwp",
        _sc("Half Day", "LWP", None, True),
        {"working": "LWP", "weekly_off": "A", "holiday": "A"},
        True,
    ),
    (
        "hp_tour",
        _sc("Present", None, "Tour", True),
        {"working": "P", "weekly_off": "POW", "holiday": "POH"},
        False,
    ),
    (
        "hp_mis",
        _sc("Present", None, "Mis Punch", True),
        {"working": "P", "weekly_off": "POW", "holiday": "POH"},
        False,
    ),
    # Full Day Present + Full Day LWP (modelled)
    (
        "fp_lwp",
        _sc("Half Day", "LWP", None, True),
        {"working": "LWP", "weekly_off": "A", "holiday": "A"},
        True,
    ),
    # Half Day OD + Half Day X
    (
        "od_el",
        _sc("Present", "EL", "Official", False),
        {"working": "EL", "weekly_off": "EL", "holiday": "EL"},
        False,
    ),
    (
        "od_cl",
        _sc("Present", "CL", "Official", False),
        {"working": "CL", "weekly_off": "CL", "holiday": "CL"},
        False,
    ),
    (
        "od_co",
        _sc("Present", "CO", "Official", False),
        {"working": "CO", "weekly_off": "CO", "holiday": "CO"},
        False,
    ),
    (
        "od_lwp",
        _sc("Half Day", "LWP", "Official", False),
        {"working": "LWP", "weekly_off": "A", "holiday": "A"},
        False,
    ),
    (
        "od_tour",
        _sc("Present", None, "Official", False),
        {"working": "P", "weekly_off": "WO", "holiday": "HO"},
        False,
    ),
    (
        "od_mis",
        _sc("Present", None, "Official", False),
        {"working": "P", "weekly_off": "WO", "holiday": "HO"},
        False,
    ),
    # Half Day EL + Half Day X
    (
        "el_cl",
        _sc("On Leave", "EL", None, False),
        {"working": "EL", "weekly_off": "EL", "holiday": "EL"},
        True,
    ),
    (
        "el_co",
        _sc("On Leave", "EL", None, False),
        {"working": "EL", "weekly_off": "EL", "holiday": "EL"},
        True,
    ),
    (
        "el_od",
        _sc("Present", "EL", "Official", False),
        {"working": "EL", "weekly_off": "EL", "holiday": "EL"},
        False,
    ),
    (
        "el_lwp",
        _sc("Half Day", "EL", None, False),
        {"working": "EL", "weekly_off": "EL", "holiday": "EL"},
        True,
    ),
    (
        "el_tour",
        _sc("Present", "EL", "Tour", False),
        {"working": "EL", "weekly_off": "EL", "holiday": "EL"},
        False,
    ),
    (
        "el_mis",
        _sc("Present", "EL", "Mis Punch", False),
        {"working": "EL", "weekly_off": "EL", "holiday": "EL"},
        False,
    ),
    (
        "el_present",
        _sc("Present", "EL", None, True),
        {"working": "EL", "weekly_off": "EL", "holiday": "EL"},
        False,
    ),
    # Half Day CL + Half Day X
    (
        "cl_el",
        _sc("On Leave", "CL", None, False),
        {"working": "CL", "weekly_off": "CL", "holiday": "CL"},
        True,
    ),
    (
        "cl_co",
        _sc("On Leave", "CL", None, False),
        {"working": "CL", "weekly_off": "CL", "holiday": "CL"},
        True,
    ),
    (
        "cl_od",
        _sc("Present", "CL", "Official", False),
        {"working": "CL", "weekly_off": "CL", "holiday": "CL"},
        False,
    ),
    (
        "cl_lwp",
        _sc("Half Day", "CL", None, False),
        {"working": "CL", "weekly_off": "CL", "holiday": "CL"},
        True,
    ),
    (
        "cl_tour",
        _sc("Present", "CL", "Tour", False),
        {"working": "CL", "weekly_off": "CL", "holiday": "CL"},
        False,
    ),
    (
        "cl_mis",
        _sc("Present", "CL", "Mis Punch", False),
        {"working": "CL", "weekly_off": "CL", "holiday": "CL"},
        False,
    ),
    (
        "cl_present",
        _sc("Present", "CL", None, True),
        {"working": "CL", "weekly_off": "CL", "holiday": "CL"},
        False,
    ),
    # Half Day CO + Half Day X
    (
        "co_cl",
        _sc("On Leave", "CO", None, False),
        {"working": "CO", "weekly_off": "CO", "holiday": "CO"},
        True,
    ),
    (
        "co_el",
        _sc("On Leave", "CO", None, False),
        {"working": "CO", "weekly_off": "CO", "holiday": "CO"},
        True,
    ),
    (
        "co_od",
        _sc("Present", "CO", "Official", False),
        {"working": "CO", "weekly_off": "CO", "holiday": "CO"},
        False,
    ),
    (
        "co_lwp",
        _sc("Half Day", "CO", None, False),
        {"working": "CO", "weekly_off": "CO", "holiday": "CO"},
        True,
    ),
    (
        "co_tour",
        _sc("Present", "CO", "Tour", False),
        {"working": "CO", "weekly_off": "CO", "holiday": "CO"},
        False,
    ),
    (
        "co_mis",
        _sc("Present", "CO", "Mis Punch", False),
        {"working": "CO", "weekly_off": "CO", "holiday": "CO"},
        False,
    ),
    (
        "co_present",
        _sc("Present", "CO", None, True),
        {"working": "CO", "weekly_off": "CO", "holiday": "CO"},
        False,
    ),
    # Half Day LWP + Half Day X
    (
        "lwp_present",
        _sc("Half Day", "LWP", None, True),
        {"working": "LWP", "weekly_off": "A", "holiday": "A"},
        True,
    ),
    (
        "lwp_el",
        _sc("Half Day", "LWP", None, False),
        {"working": "LWP", "weekly_off": "A", "holiday": "A"},
        True,
    ),
    (
        "lwp_cl",
        _sc("Half Day", "LWP", None, False),
        {"working": "LWP", "weekly_off": "A", "holiday": "A"},
        True,
    ),
    (
        "lwp_co",
        _sc("Half Day", "LWP", None, False),
        {"working": "LWP", "weekly_off": "A", "holiday": "A"},
        True,
    ),
    (
        "lwp_od",
        _sc("Half Day", "LWP", "Official", False),
        {"working": "LWP", "weekly_off": "A", "holiday": "A"},
        False,
    ),
    (
        "lwp_tour",
        _sc("Half Day", "LWP", "Tour", False),
        {"working": "LWP", "weekly_off": "A", "holiday": "A"},
        False,
    ),
    (
        "lwp_mis",
        _sc("Half Day", "LWP", "Mis Punch", False),
        {"working": "LWP", "weekly_off": "A", "holiday": "A"},
        False,
    ),
    # Half Day Mis Punch + Half Day X
    (
        "mis_el",
        _sc("Present", "EL", "Mis Punch", False),
        {"working": "EL", "weekly_off": "EL", "holiday": "EL"},
        False,
    ),
    (
        "mis_cl",
        _sc("Present", "CL", "Mis Punch", False),
        {"working": "CL", "weekly_off": "CL", "holiday": "CL"},
        False,
    ),
    (
        "mis_co",
        _sc("Present", "CO", "Mis Punch", False),
        {"working": "CO", "weekly_off": "CO", "holiday": "CO"},
        False,
    ),
    (
        "mis_tour",
        _sc("Present", None, "Mis Punch", False),
        {"working": "P", "weekly_off": "WO", "holiday": "HO"},
        False,
    ),
    (
        "mis_od",
        _sc("Present", None, "Mis Punch", False),
        {"working": "P", "weekly_off": "WO", "holiday": "HO"},
        False,
    ),
]


class TestMultiRecordTagMatrix(TestCase):
    def test_tag_per_scenario_and_day_context(self):
        for label, scenario, expected_tags, _ in _MULTI_RECORD_MATRIX:
            for context, expected_tag in expected_tags.items():
                with self.subTest(scenario=label, day=context):
                    self.assertEqual(
                        _run_update_attendance_tag(scenario, context), expected_tag
                    )

    def test_absence_side_per_scenario(self):
        for label, scenario, _, expected_absence_side in _MULTI_RECORD_MATRIX:
            with self.subTest(scenario=label):
                self.assertEqual(
                    _run_is_sandwich_absence_side(scenario), expected_absence_side
                )
