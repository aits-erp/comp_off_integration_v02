from importlib import import_module
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch


attendance_request = import_module("real_group_hrms.doc_events.attendace_request")


class TestAttendanceRequestValidation(TestCase):
    def test_rejected_request_requires_reason(self):
        doc = SimpleNamespace(
            workflow_state="Rejected by HOD",
            custom_reason_for_rejection="",
        )

        with patch.object(attendance_request.frappe, "_", side_effect=lambda message: message):
            with patch.object(attendance_request.frappe, "throw", side_effect=Exception) as throw:
                with self.assertRaises(Exception):
                    attendance_request.validate_workflow_state(doc)

        throw.assert_called_once_with("Kindly set the reason for rejection")

    def test_rejected_request_allows_reason(self):
        doc = SimpleNamespace(
            workflow_state="Rejected by HR",
            custom_reason_for_rejection="Not applicable",
        )

        with patch.object(attendance_request.frappe, "throw") as throw:
            attendance_request.validate_workflow_state(doc)

        throw.assert_not_called()

    def test_non_rejected_request_does_not_require_reason(self):
        doc = SimpleNamespace(
            workflow_state="Pending at HR",
            custom_reason_for_rejection="",
        )

        with patch.object(attendance_request.frappe, "throw") as throw:
            attendance_request.validate_workflow_state(doc)

        throw.assert_not_called()

    def test_validate_date_ignores_rejected_attendance_request_states(self):
        doc = SimpleNamespace(
            employee="EMP-001",
            from_date="2026-06-20",
            to_date="2026-06-20",
            name="new-attendance-request",
            half_day=0,
            half_day_date=None,
            custom_half_type="",
        )

        def get_all(doctype, filters, fields):
            if doctype == "Leave Application":
                return []

            self.assertEqual(doctype, "Attendance Request")
            self.assertIn("Rejected by HOD", filters["workflow_state"][1])
            return []

        with patch.object(attendance_request.frappe, "get_all", side_effect=get_all):
            with patch.object(attendance_request.frappe, "throw") as throw:
                attendance_request.validate_date(doc)

        throw.assert_not_called()

    def test_mis_punch_limit_zero_allows_unlimited_requests(self):
        doc = SimpleNamespace(employee="EMP-001", from_date="2026-06-06", name="HR-ARQ-001")

        with patch.object(attendance_request, "get_allowed_mis_punch_days", return_value=0):
            with patch.object(attendance_request, "get_monthly_mis_punch_request_count") as count:
                with patch.object(attendance_request.frappe, "throw") as throw:
                    attendance_request.validate_mis_punch_monthly_limit(doc)

        count.assert_not_called()
        throw.assert_not_called()

    def test_mis_punch_limit_allows_request_when_count_is_below_limit(self):
        doc = SimpleNamespace(employee="EMP-001", from_date="2026-06-06", name="HR-ARQ-001")

        with patch.object(attendance_request, "get_allowed_mis_punch_days", return_value=3):
            with patch.object(attendance_request, "get_monthly_mis_punch_request_count", return_value=2):
                with patch.object(attendance_request.frappe, "throw") as throw:
                    attendance_request.validate_mis_punch_monthly_limit(doc)

        throw.assert_not_called()

    def test_mis_punch_limit_rejects_request_when_count_reaches_limit(self):
        doc = SimpleNamespace(employee="EMP-001", from_date="2026-06-06", name="HR-ARQ-001")

        with patch.object(attendance_request, "get_allowed_mis_punch_days", return_value=3):
            with patch.object(attendance_request, "get_monthly_mis_punch_request_count", return_value=3):
                with patch.object(attendance_request.frappe, "_", side_effect=lambda message: message):
                    with patch.object(attendance_request.frappe, "throw", side_effect=Exception) as throw:
                        with self.assertRaises(Exception):
                            attendance_request.validate_mis_punch_monthly_limit(doc)

        throw.assert_called_once_with(attendance_request.MIS_PUNCH_LIMIT_REACHED_MESSAGE)

    def test_mis_punch_rejects_request_when_checkin_and_checkout_exist(self):
        doc = SimpleNamespace(employee="EMP-001", from_date="2026-06-06")
        checkins = [
            SimpleNamespace(log_type="IN", time="2026-06-06 09:00:00"),
            SimpleNamespace(log_type="OUT", time="2026-06-06 18:00:00"),
        ]

        with patch.object(attendance_request, "get_mis_punch_checkins", return_value=checkins):
            with patch.object(attendance_request.frappe, "_", side_effect=lambda message: message):
                with patch.object(attendance_request.frappe, "throw", side_effect=Exception) as throw:
                    with self.assertRaises(Exception):
                        attendance_request.validate_mis_punch_checkins(doc)

        throw.assert_called_once_with(attendance_request.MIS_PUNCH_VALID_PAIR_EXISTS_MESSAGE)

    def test_mis_punch_rejects_request_when_no_checkin_or_checkout_exists(self):
        doc = SimpleNamespace(employee="EMP-001", from_date="2026-06-06")

        with patch.object(attendance_request, "get_mis_punch_checkins", return_value=[]):
            with patch.object(attendance_request.frappe, "_", side_effect=lambda message: message):
                with patch.object(attendance_request.frappe, "throw", side_effect=Exception) as throw:
                    with self.assertRaises(Exception):
                        attendance_request.validate_mis_punch_checkins(doc)

        throw.assert_called_once_with(attendance_request.MIS_PUNCH_NO_CHECKIN_EXISTS_MESSAGE)

    def test_mis_punch_allows_request_when_checkout_is_missing(self):
        doc = SimpleNamespace(employee="EMP-001", from_date="2026-06-06")
        checkins = [SimpleNamespace(log_type="IN", time="2026-06-06 09:00:00")]

        with patch.object(attendance_request, "get_mis_punch_checkins", return_value=checkins):
            with patch.object(attendance_request.frappe, "throw") as throw:
                attendance_request.validate_mis_punch_checkins(doc)

        throw.assert_not_called()

    def test_mis_punch_allows_request_when_checkin_is_missing(self):
        doc = SimpleNamespace(employee="EMP-001", from_date="2026-06-06")
        checkins = [SimpleNamespace(log_type="OUT", time="2026-06-06 18:00:00")]

        with patch.object(attendance_request, "get_mis_punch_checkins", return_value=checkins):
            with patch.object(attendance_request.frappe, "throw") as throw:
                attendance_request.validate_mis_punch_checkins(doc)

        throw.assert_not_called()

    def test_mis_punch_checkins_are_fetched_by_shift_start_and_request_shift(self):
        with patch.object(attendance_request.frappe, "get_all", return_value=[]) as get_all:
            attendance_request.get_mis_punch_checkins("12730", "2026-06-15", "N")

        _, kwargs = get_all.call_args
        self.assertEqual(kwargs["filters"]["employee"], "12730")
        self.assertEqual(kwargs["filters"]["shift"], "N")
        self.assertIn("shift_start", kwargs["filters"])
        self.assertNotIn("or_filters", kwargs)


leave_application_override = import_module("real_group_hrms.overrides.leave_application")
attendance_request_override = import_module("real_group_hrms.overrides.attendance_request")


class TestCancelAttendanceReappliesOnlySubmittedRequests(TestCase):
    """Cancelling a Leave Application rebuilds each affected day and re-applies
    any Attendance Request covering it.

    Regression: the request lookup had no docstatus filter, so it could return a
    CANCELLED request; linking Attendance to it raised CancelledLinkError and
    rolled back the whole cancellation (live case: Leave Application
    RB-LAP-24-0001857 vs cancelled Attendance Request HR-ARQ-26-07-00132).

    It also used get_value(), returning only ONE request, so a date carrying two
    submitted half-day requests (First Half + Second Half) had the second one
    silently dropped.
    """

    def _run_cancel_attendance(self, request_rows):
        """Drive the real cancel_attendance() with its data-access boundary
        mocked. Returns (get_all filters used for Attendance Request,
        list of requests that create_or_update_attendance was invoked on)."""
        mod = leave_application_override
        applied = []
        captured_filters = {}

        doc = SimpleNamespace(
            docstatus=2,
            name="RB-LAP-TEST-1",
            employee="11906",
            from_date="2026-06-24",
            to_date="2026-06-24",
        )

        def get_all(doctype, *args, **kwargs):
            if doctype == "Attendance Request":
                captured_filters.update(kwargs.get("filters", {}))
                return [row["name"] for row in request_rows]
            return []  # Employee Checkin

        real_get_doc = mod.frappe.get_doc

        def get_doc(doctype, name=None, *args, **kwargs):
            if doctype == "Attendance":
                return SimpleNamespace(docstatus=2, cancel=lambda: None)
            if doctype == "Attendance Request":
                request = SimpleNamespace(name=name)
                request.create_or_update_attendance = (
                    lambda date, _n=name: applied.append(_n)
                )
                return request
            # Anything else (e.g. frappe's own System Settings lookup) must keep
            # working normally.
            if name is None:
                return real_get_doc(doctype)
            return real_get_doc(doctype, name, *args, **kwargs)

        # Keep the real DocType so the pypika filter expressions still build,
        # and mock only the execution of the query.
        qb = MagicMock()
        qb.DocType.side_effect = mod.frappe.qb.DocType
        qb.from_.return_value.select.return_value.where.return_value.run.return_value = [
            mod.frappe._dict(name="HR-ATT-TEST-1", attendance_date="2026-06-24")
        ]

        with patch.object(mod.frappe, "qb", qb), \
            patch.object(mod.frappe, "get_all", side_effect=get_all), \
            patch.object(mod.frappe, "get_doc", side_effect=get_doc), \
            patch.object(mod.frappe, "flags", mod.frappe._dict(in_reprocess_attendance=False)), \
            patch.object(mod, "create_attendance"):
            mod.LeaveApplicationOverride.cancel_attendance(doc)

        return captured_filters, applied

    def test_lookup_is_restricted_to_submitted_requests(self):
        captured_filters, _ = self._run_cancel_attendance([])
        self.assertEqual(captured_filters.get("docstatus"), 1)

    def test_single_submitted_request_is_reapplied_once(self):
        _, applied = self._run_cancel_attendance([{"name": "HR-ARQ-1"}])
        self.assertEqual(applied, ["HR-ARQ-1"])

    def test_both_half_day_requests_on_one_date_are_reapplied(self):
        _, applied = self._run_cancel_attendance(
            [{"name": "HR-ARQ-26-07-00131"}, {"name": "HR-ARQ-26-07-00134"}]
        )
        self.assertEqual(applied, ["HR-ARQ-26-07-00131", "HR-ARQ-26-07-00134"])

    def test_no_request_for_the_date_applies_nothing(self):
        _, applied = self._run_cancel_attendance([])
        self.assertEqual(applied, [])


class TestCreateOrUpdateAttendanceDocstatusGuard(TestCase):
    def _request(self, docstatus):
        request = attendance_request_override.AttendanceRequestOverride.__new__(
            attendance_request_override.AttendanceRequestOverride
        )
        request.docstatus = docstatus
        return request

    def test_cancelled_request_does_not_touch_attendance(self):
        request = self._request(2)
        with patch.object(
            attendance_request_override.AttendanceRequestOverride,
            "get_attendance_record",
        ) as get_attendance_record:
            request.create_or_update_attendance("2026-06-24")
        get_attendance_record.assert_not_called()

    def test_draft_request_does_not_touch_attendance(self):
        request = self._request(0)
        with patch.object(
            attendance_request_override.AttendanceRequestOverride,
            "get_attendance_record",
        ) as get_attendance_record:
            request.create_or_update_attendance("2026-06-24")
        get_attendance_record.assert_not_called()

    def test_submitted_request_proceeds(self):
        request = self._request(1)
        with patch.object(
            attendance_request_override.AttendanceRequestOverride,
            "get_attendance_record",
            return_value=None,
        ) as get_attendance_record, patch.object(
            attendance_request_override.AttendanceRequestOverride,
            "get_attendance_status",
            return_value="Present",
        ), patch.object(
            attendance_request_override.frappe, "new_doc"
        ) as new_doc:
            request.employee = "11906"
            request.shift = None
            request.company = "RIPL"
            request.name = "HR-ARQ-1"
            request.create_or_update_attendance("2026-06-24")

        get_attendance_record.assert_called_once()
        new_doc.assert_called_once_with("Attendance")
