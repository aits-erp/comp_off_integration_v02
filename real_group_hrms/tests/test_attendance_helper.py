from unittest import TestCase
from types import SimpleNamespace

import frappe
from frappe.utils import get_datetime

from real_group_hrms.helper.attendance_helper import (
    calculate_working_hours_for_attendance,
    get_attendance_status_from_working_hours,
    get_first_checkin_shift,
    get_specific_multi_checkin_override_fields,
    has_valid_in_out_pair,
)


class TestAttendanceHelper(TestCase):
    def test_negative_processed_hours_fall_back_to_original_checkin_time(self):
        logs = [
            frappe._dict(
                log_type="IN",
                time=get_datetime("2026-03-10 08:09:15"),
                custom_processed_time=get_datetime("2026-03-10 08:30:00"),
            ),
            frappe._dict(
                log_type="OUT",
                time=get_datetime("2026-03-10 08:09:19"),
                custom_processed_time=get_datetime("2026-03-10 08:09:19"),
            ),
        ]

        working_hours, in_time, out_time = calculate_working_hours_for_attendance(logs)

        self.assertEqual(working_hours, 0.0)
        self.assertEqual(in_time, get_datetime("2026-03-10 08:09:15"))
        self.assertEqual(out_time, get_datetime("2026-03-10 08:09:19"))

    def test_original_checkin_time_is_not_used_when_processed_hours_are_positive(self):
        logs = [
            frappe._dict(
                log_type="IN",
                time=get_datetime("2026-03-10 08:00:00"),
                custom_processed_time=get_datetime("2026-03-10 09:00:00"),
            ),
            frappe._dict(
                log_type="OUT",
                time=get_datetime("2026-03-10 17:00:00"),
                custom_processed_time=get_datetime("2026-03-10 17:00:00"),
            ),
        ]

        working_hours, in_time, out_time = calculate_working_hours_for_attendance(logs)

        self.assertEqual(working_hours, 8.0)
        self.assertEqual(in_time, get_datetime("2026-03-10 09:00:00"))
        self.assertEqual(out_time, get_datetime("2026-03-10 17:00:00"))

    def test_specific_multi_checkin_override_uses_first_checkin_shift_and_combined_hours(
        self,
    ):
        logs = [
            frappe._dict(
                log_type="IN",
                shift="B",
                time=get_datetime("2026-03-10 13:55:22"),
                custom_processed_time=get_datetime("2026-03-10 13:55:22"),
            ),
            frappe._dict(
                log_type="OUT",
                shift="B",
                time=get_datetime("2026-03-10 22:00:33"),
                custom_processed_time=get_datetime("2026-03-10 22:00:33"),
            ),
            frappe._dict(
                log_type="IN",
                shift="C",
                time=get_datetime("2026-03-10 22:01:13"),
                custom_processed_time=get_datetime("2026-03-10 22:01:13"),
            ),
            frappe._dict(
                log_type="OUT",
                shift="C",
                time=get_datetime("2026-03-11 03:01:00"),
                custom_processed_time=get_datetime("2026-03-11 03:01:00"),
            ),
        ]
        shift = SimpleNamespace(
            name="B",
            custom_working_hours_threshold_for_present="7:44:59",
            custom_working_hours_threshold_for_half_day="3:50:01",
            custom_working_hours_threshold_for_absent="3:50:00",
        )

        override = get_specific_multi_checkin_override_fields(logs, shift)

        self.assertEqual(get_first_checkin_shift(logs), "B")
        self.assertEqual(override["status"], "Present")
        self.assertEqual(override["shift"], "B")
        self.assertEqual(override["in_time"], get_datetime("2026-03-10 13:55:22"))
        self.assertEqual(override["out_time"], get_datetime("2026-03-11 03:01:00"))
        self.assertEqual(override["working_hours"], 13.09)
        self.assertFalse(override["late_entry"])
        self.assertFalse(override["early_exit"])

    def test_specific_multi_checkin_override_marks_half_day_from_combined_pairs(self):
        logs = [
            frappe._dict(
                log_type="IN",
                shift="G",
                time=get_datetime("2026-03-10 09:00:00"),
                custom_processed_time=get_datetime("2026-03-10 09:00:00"),
            ),
            frappe._dict(
                log_type="OUT",
                shift="G",
                time=get_datetime("2026-03-10 11:00:00"),
                custom_processed_time=get_datetime("2026-03-10 11:00:00"),
            ),
            frappe._dict(
                log_type="IN",
                shift="G",
                time=get_datetime("2026-03-10 13:00:00"),
                custom_processed_time=get_datetime("2026-03-10 13:00:00"),
            ),
            frappe._dict(
                log_type="OUT",
                shift="G",
                time=get_datetime("2026-03-10 18:01:00"),
                custom_processed_time=get_datetime("2026-03-10 18:01:00"),
            ),
        ]
        shift = SimpleNamespace(
            name="G",
            custom_working_hours_threshold_for_present="8:00:00",
            custom_working_hours_threshold_for_half_day="4:00:00",
            custom_working_hours_threshold_for_absent="3:59:59",
        )

        override = get_specific_multi_checkin_override_fields(logs, shift)

        self.assertEqual(override["status"], "Half Day")
        self.assertEqual(override["shift"], "G")
        self.assertEqual(override["in_time"], get_datetime("2026-03-10 09:00:00"))
        self.assertEqual(override["out_time"], get_datetime("2026-03-10 18:01:00"))
        self.assertEqual(override["working_hours"], 7.02)


# ---------------------------------------------------------------------------
# Single-record combination matrix (helper / presence layer).
#
# The helper layer's job is to decide the *physical presence* status of a day
# from its check-ins alone (Present / Half Day / Absent) - it does NOT know
# about leave applications or attendance requests; those are layered on later
# by the doc-event hooks (see TestSingleRecordTagMatrix in
# test_attendance_doc_events.py for the tag side of the same scenarios).
#
# So for each single-record scenario this matrix characterises what the helper
# contributes: whether the scenario's check-ins form a valid IN/OUT pair, and
# if so, the working-hours status band it lands in. Leave-only, attendance-
# request-only and mis-punch days have no valid pair, so the helper leaves them
# to be marked Absent and the real status is decided by the leave/request layer.
#
#   Present = full physical presence (>= present threshold)
#   Half Day = partial physical presence (>= half-day, < present)
#   None with valid_pair False = helper marks the day Absent; final status is
#     supplied by the leave/attendance-request layer.
# ---------------------------------------------------------------------------

_SHIFT = SimpleNamespace(
    name="STD",
    custom_working_hours_threshold_for_present="8:00:00",
    custom_working_hours_threshold_for_half_day="4:00:00",
    custom_working_hours_threshold_for_absent="3:59:59",
)


def _pair(minutes_worked):
    start = get_datetime("2026-06-25 09:00:00")
    return [
        frappe._dict(log_type="IN", time=start),
        frappe._dict(log_type="OUT", time=start),
    ], minutes_worked


# label -> (checkin logs, working_hours, expected_valid_pair, expected_status_if_valid)
_SINGLE_RECORD_PRESENCE = [
    ("full_present", _pair(9)[0], 9.0, True, "Present"),
    ("half_present", _pair(5)[0], 5.0, True, "Half Day"),
    ("full_od", [], 0.0, False, None),
    ("half_od", [], 0.0, False, None),
    ("full_el", [], 0.0, False, None),
    ("full_cl", [], 0.0, False, None),
    ("full_co", [], 0.0, False, None),
    ("full_lwp", [], 0.0, False, None),
    (
        "full_mispunch",
        [frappe._dict(log_type="IN", time=get_datetime("2026-06-25 09:00:00"))],
        0.0,
        False,
        None,
    ),
    (
        "half_mispunch",
        [frappe._dict(log_type="IN", time=get_datetime("2026-06-25 09:00:00"))],
        0.0,
        False,
        None,
    ),
]


class TestSingleRecordPresenceMatrix(TestCase):
    def test_valid_in_out_pair_per_scenario(self):
        for label, logs, _hours, expected_valid, _status in _SINGLE_RECORD_PRESENCE:
            with self.subTest(scenario=label):
                self.assertEqual(has_valid_in_out_pair(logs), expected_valid)

    def test_presence_status_band_for_checkin_scenarios(self):
        for (
            label,
            logs,
            hours,
            expected_valid,
            expected_status,
        ) in _SINGLE_RECORD_PRESENCE:
            if not expected_valid:
                continue
            with self.subTest(scenario=label):
                self.assertEqual(
                    get_attendance_status_from_working_hours(hours, _SHIFT),
                    expected_status,
                )


# ---------------------------------------------------------------------------
# Multi-record combination matrix (helper / presence layer).
#
# Same 47 two-item combinations as TestMultiRecordTagMatrix in
# test_attendance_doc_events.py, but characterising only what the HELPER layer
# contributes: the physical-presence decision from check-ins. The leave /
# attendance-request resolution (which produces the final tag) is a doc-event
# concern and is covered there, not here.
#
# Each combo's physical component is one of:
#   "full" -> a full day of check-ins        -> valid pair, Present band
#   "half" -> a half day of check-ins        -> valid pair, Half Day band
#   "none" -> no valid check-in pair (leave / attendance-request only, or a
#             lone mis-punch) -> helper marks Absent; the real status comes
#             from the leave / request layer.
# ---------------------------------------------------------------------------

# label -> physical component ("full" | "half" | "none")
_MULTI_RECORD_PRESENCE = [
    ("hp_od", "half"),
    ("hp_el", "half"),
    ("hp_cl", "half"),
    ("hp_co", "half"),
    ("hp_lwp", "half"),
    ("hp_tour", "half"),
    ("hp_mis", "half"),
    ("fp_lwp", "full"),
    ("od_el", "none"),
    ("od_cl", "none"),
    ("od_co", "none"),
    ("od_lwp", "none"),
    ("od_tour", "none"),
    ("od_mis", "none"),
    ("el_cl", "none"),
    ("el_co", "none"),
    ("el_od", "none"),
    ("el_lwp", "none"),
    ("el_tour", "none"),
    ("el_mis", "none"),
    ("el_present", "half"),
    ("cl_el", "none"),
    ("cl_co", "none"),
    ("cl_od", "none"),
    ("cl_lwp", "none"),
    ("cl_tour", "none"),
    ("cl_mis", "none"),
    ("cl_present", "half"),
    ("co_cl", "none"),
    ("co_el", "none"),
    ("co_od", "none"),
    ("co_lwp", "none"),
    ("co_tour", "none"),
    ("co_mis", "none"),
    ("co_present", "half"),
    ("lwp_present", "half"),
    ("lwp_el", "none"),
    ("lwp_cl", "none"),
    ("lwp_co", "none"),
    ("lwp_od", "none"),
    ("lwp_tour", "none"),
    ("lwp_mis", "none"),
    ("mis_el", "none"),
    ("mis_cl", "none"),
    ("mis_co", "none"),
    ("mis_tour", "none"),
    ("mis_od", "none"),
]

_PHYSICAL_COMPONENT = {
    "full": (
        [
            frappe._dict(log_type="IN", time=get_datetime("2026-06-25 09:00:00")),
            frappe._dict(log_type="OUT", time=get_datetime("2026-06-25 18:00:00")),
        ],
        9.0,
        True,
        "Present",
    ),
    "half": (
        [
            frappe._dict(log_type="IN", time=get_datetime("2026-06-25 09:00:00")),
            frappe._dict(log_type="OUT", time=get_datetime("2026-06-25 14:00:00")),
        ],
        5.0,
        True,
        "Half Day",
    ),
    "none": ([], 0.0, False, None),
}


class TestMultiRecordPresenceMatrix(TestCase):
    def test_valid_in_out_pair_per_scenario(self):
        for label, component in _MULTI_RECORD_PRESENCE:
            logs, _hours, expected_valid, _status = _PHYSICAL_COMPONENT[component]
            with self.subTest(scenario=label):
                self.assertEqual(has_valid_in_out_pair(logs), expected_valid)

    def test_presence_status_band_for_checkin_scenarios(self):
        for label, component in _MULTI_RECORD_PRESENCE:
            logs, hours, expected_valid, expected_status = _PHYSICAL_COMPONENT[
                component
            ]
            if not expected_valid:
                continue
            with self.subTest(scenario=label):
                self.assertEqual(
                    get_attendance_status_from_working_hours(hours, _SHIFT),
                    expected_status,
                )
