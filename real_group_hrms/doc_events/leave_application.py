from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import (
    add_days,
    cint,
    date_diff,
    formatdate,
    get_datetime,
    get_link_to_form,
    get_timedelta,
    getdate,
)

from real_group_hrms.utils import (
    half_types_match,
    is_holiday_for_employee,
    normalize_half_type,
)


EL_CL_REJECTED_STATES = ["Cancelled", "Rejected by HOD", "Rejected by HR"]


def validate(doc, method=None):
    if is_salary_processed(doc):
        frappe.throw(
            frappe._(
                "Leave Application cannot be created, updated, or approved because a Salary Slip already exists for this period."
            )
        )

    validate_employee_not_resigned(doc)
    validate_change_request_day(doc)
    validate_cl(doc)
    validate_el_and_cl(doc)
    validate_compensation_leave(doc)
    validate_comp_off_source(doc)
    validate_workflow_state(doc)
    validate_attendance(doc)
    validate_cross_month_leave(doc)
    validate_attendance_request(doc)
    validate_leave_overlap(doc)
    validate_leave_balance(doc)


def validate_employee_not_resigned(doc):
    if not doc.is_new():
        return

    resignation_letter_date, relieving_date = frappe.db.get_value(
        "Employee",
        doc.employee,
        ["resignation_letter_date", "relieving_date"],
    )

    set_dates = [d for d in (resignation_letter_date, relieving_date) if d]
    cutoff_date = min(set_dates) if set_dates else None

    if cutoff_date and getdate(doc.to_date) >= getdate(cutoff_date):
        frappe.throw(
            frappe._(
                "Employee {0} cannot apply for leave on or after {1} as Resignation Letter Date/Relieving Date is set in the Employee master."
            ).format(doc.employee, formatdate(cutoff_date))
        )


def before_cancel(doc, method=None):
    if is_salary_processed(doc):
        frappe.throw(
            frappe._(
                "Cannot cancel: a Salary Slip (draft or submitted) already exists for this period."
            ),
            SandwichPolicyError,
        )


def before_delete(doc, method=None):
    if is_salary_processed(doc):
        frappe.throw(
            frappe._(
                "Cannot delete: a Salary Slip (draft or submitted) already exists for this period."
            )
        )


def is_salary_processed(doc):
    if not (doc.employee and doc.from_date and doc.to_date):
        return False

    return frappe.db.exists(
        "Salary Slip",
        {
            "employee": doc.employee,
            "start_date": ["<=", doc.to_date],
            "end_date": [">=", doc.from_date],
            "docstatus": ["!=", 2],
        },
    )


def validate_compensation_leave(doc):
    """Comp-Off duration is validated against its selected source credits below.

    The former single-day restriction made the existing HRMS Compensatory
    Leave Request flow incompatible with multiple earned holiday credits.
    """
    return


def validate_comp_off_source(doc):
    """Keep each Comp-Off leave day traceable to one unused earned credit."""
    if not (
        doc.leave_type
        and frappe.db.get_value("Leave Type", doc.leave_type, "is_compensatory")
    ):
        return

    source_rows = doc.get("custom_comp_off_source_request") or []
    if isinstance(source_rows, str):
        # Supports records created by the former single-Link field until the
        # migration patch has converted them to child rows.
        source_names = [source_rows]
    else:
        source_names = [
            row.compensatory_leave_request
            for row in source_rows
            if row.compensatory_leave_request
        ]

    if not source_names:
        frappe.throw(
            _("Select the approved Compensatory Leave Request(s) that earned this leave."),
            title=_("Compensatory Leave Request Required"),
        )

    if len(source_names) != len(set(source_names)):
        frappe.throw(_("The same Compensatory Leave Request cannot be selected more than once."))

    if doc.total_leave_days and len(source_names) != doc.total_leave_days:
        frappe.throw(
            _("Select exactly {0} Worked Holiday(s) to match the {0} day(s) of leave applied for.").format(
                doc.total_leave_days
            ),
            title=_("Worked Holiday Count Mismatch"),
        )

    used_by = {
        row.compensatory_leave_request: row.parent
        for row in frappe.db.sql(
            """
            SELECT source.compensatory_leave_request, source.parent
            FROM `tabComp Off Source Request` AS source
            INNER JOIN `tabLeave Application` AS application ON application.name = source.parent
            WHERE source.parenttype = 'Leave Application'
              AND application.docstatus = 1
              AND application.name != %(name)s
            """,
            {"name": doc.name or ""},
            as_dict=True,
        )
    }

    for source_name in source_names:
        source = frappe.db.get_value(
            "Compensatory Leave Request",
            source_name,
            ["employee", "leave_type", "work_from_date", "work_end_date", "docstatus", "status"],
            as_dict=True,
        )
        if not source:
            frappe.throw(_("The selected Compensatory Leave Request {0} does not exist.").format(source_name))
        if source.docstatus != 1 or source.status == "Expired":
            frappe.throw(_("Compensatory Leave Request {0} must be submitted and unexpired.").format(source_name))
        if source.employee != doc.employee:
            frappe.throw(_("Compensatory Leave Request {0} belongs to another employee.").format(source_name))
        if source.leave_type != doc.leave_type:
            frappe.throw(_("The leave type of {0} does not match this Leave Application.").format(source_name))
        if getdate(source.work_from_date) != getdate(source.work_end_date):
            frappe.throw(_("Compensatory Leave Request {0} must cover a single worked date.").format(source_name))
        if getdate(doc.from_date) <= getdate(source.work_end_date):
            frappe.throw(
                _("Compensatory Off can be used only after the worked holiday date linked to {0}.").format(
                    source_name
                )
            )
        if source_name in used_by:
            frappe.throw(
                _("Compensatory Leave Request {0} is already linked to Leave Application {1}.").format(
                    source_name, frappe.bold(used_by[source_name])
                )
            )


def validate_workflow_state(doc):
    if doc.workflow_state in (
        "Rejected by HOD",
        "Rejected by HR",
        "Rejected at Gate",
    ) and (
        doc.custom_reason_for_rejection == "" or doc.custom_reason_for_rejection is None
    ):
        frappe.throw(frappe._("Kindly set the reason for rejection"))


def validate_attendance(doc):
    if frappe.flags.in_reprocess_attendance:
        return
    if doc.from_date == doc.to_date:
        att_exist = frappe.db.exists(
            "Attendance",
            {
                "employee": doc.employee,
                "attendance_date": doc.from_date,
                "status": "Present",
                "docstatus": ["!=", 2],
            },
        )
        if att_exist:
            frappe.throw(
                frappe._(
                    "Attendance is already marked for the Employee {0} on {1}"
                ).format(doc.employee, format_display_date(doc.from_date))
            )
    else:
        att_dates = []
        cur_date = doc.from_date
        while cur_date <= doc.to_date:
            att_dates.append(cur_date)
            cur_date = add_days(cur_date, days=1)
        for date in att_dates:
            att_exist = frappe.db.exists(
                "Attendance",
                {
                    "employee": doc.employee,
                    "attendance_date": date,
                    "status": "Present",
                    "docstatus": ["!=", 2],
                },
            )
            if att_exist:
                frappe.throw(
                    frappe._(
                        "Attendance is already marked for the Employee {0} on {1}"
                    ).format(doc.employee, format_display_date(date))
                )


def validate_cross_month_leave(doc):
    from_date = getdate(doc.from_date)
    to_date = getdate(doc.to_date)

    if from_date.month != to_date.month or from_date.year != to_date.year:
        frappe.throw(frappe._("Leave application cannot span across multiple months."))


def validate_cl(doc):
    leave_type = doc.leave_type
    is_based_on_working_days = frappe.db.get_value(
        "Leave Type", leave_type, "custom_restrict_leave_adjacent_to_holiday"
    )
    if is_based_on_working_days:
        prev_day = add_days(doc.from_date, -1)
        next_day = add_days(doc.to_date, 1)

        prev_day_info = is_holiday_for_employee(doc.employee, prev_day) or {}
        next_day_info = is_holiday_for_employee(doc.employee, next_day) or {}

        is_prev_day_holiday = bool(prev_day_info) and not prev_day_info.get(
            "is_weekly_off"
        )
        is_next_day_holiday = bool(next_day_info) and not next_day_info.get(
            "is_weekly_off"
        )

        if is_prev_day_holiday or is_next_day_holiday:
            frappe.throw(
                frappe._(
                    "Casual Leave cannot be applied before or after a holiday. Please adjust your leave dates."
                )
            )


def validate_el_and_cl(doc):
    if not is_el_or_cl(doc.leave_type):
        return

    for leave in get_relevant_opposite_el_cl_leaves(doc):
        if not is_opposite_el_cl(doc.leave_type, leave.leave_type):
            continue

        if leaves_overlap(doc, leave):
            frappe.throw(
                _(
                    "EL and CL cannot be applied on the same date. One Present day is mandatory between EL and CL."
                )
            )

        earlier, later = order_leaves_by_date(doc, leave)
        if not has_valid_el_cl_separator(doc.employee, earlier, later):
            frappe.throw(
                _(
                    "EL and CL cannot be applied. One Present day is mandatory between EL and CL from {0} to {1}.".format(
                        format_display_date(earlier.to_date),
                        format_display_date(later.from_date),
                    )
                )
            )


def is_el_or_cl(leave_type):
    leave_type = (leave_type or "").lower()
    return "earned" in leave_type or "casual" in leave_type


def is_opposite_el_cl(current_leave_type, other_leave_type):
    current_leave_type = (current_leave_type or "").lower()
    other_leave_type = (other_leave_type or "").lower()
    return (
        ("earned" in current_leave_type and "casual" in other_leave_type)
        or ("casual" in current_leave_type and "earned" in other_leave_type)
    )


def get_relevant_opposite_el_cl_leaves(doc):
    fields = [
        "name",
        "leave_type",
        "from_date",
        "to_date",
        "half_day",
        "half_day_date",
        "custom_half_type",
    ]
    base_filters = {
        "employee": doc.employee,
        "docstatus": ["!=", 2],
        "workflow_state": ["not in", EL_CL_REJECTED_STATES],
        "name": ["!=", doc.name],
        "leave_type": ["like", get_opposite_el_cl_pattern(doc.leave_type)],
    }

    leaves = []
    for extra_filters, order_by, limit in (
        (
            {
                "from_date": ["<=", doc.to_date],
                "to_date": [">=", doc.from_date],
            },
            None,
            None,
        ),
        ({"to_date": ["<", doc.from_date]}, "to_date desc, from_date desc", 1),
        ({"from_date": [">", doc.to_date]}, "from_date asc, to_date asc", 1),
    ):
        filters = base_filters.copy()
        filters.update(extra_filters)
        leaves.extend(
            frappe.get_all(
                "Leave Application",
                filters=filters,
                fields=fields,
                order_by=order_by,
                limit=limit,
            )
        )

    unique_leaves = []
    seen = set()
    for leave in leaves:
        if leave.name in seen:
            continue
        seen.add(leave.name)
        unique_leaves.append(leave)
    return unique_leaves


def get_opposite_el_cl_pattern(leave_type):
    leave_type = (leave_type or "").lower()
    if "earned" in leave_type:
        return "%Casual%"
    if "casual" in leave_type:
        return "%Earned%"
    return "%"


def leaves_overlap(first, second):
    return getdate(first.from_date) <= getdate(second.to_date) and getdate(
        second.from_date
    ) <= getdate(first.to_date)


def order_leaves_by_date(first, second):
    first_start = getdate(first.from_date)
    second_start = getdate(second.from_date)
    if first_start < second_start:
        return first, second
    if first_start > second_start:
        return second, first
    if getdate(first.to_date) <= getdate(second.to_date):
        return first, second
    return second, first


def has_valid_el_cl_separator(employee, earlier, later):
    earlier_end = getdate(earlier.to_date)
    later_start = getdate(later.from_date)

    after_earlier_half = get_required_present_half_after_leave(earlier, earlier_end)
    if after_earlier_half and has_present_or_approved_request(
        employee, earlier_end, after_earlier_half
    ):
        return True

    current_date = add_days(earlier_end, 1)
    while current_date < later_start:
        if has_present_or_approved_request(employee, current_date):
            return True
        current_date = add_days(current_date, 1)

    before_later_half = get_required_present_half_before_leave(later, later_start)
    if before_later_half and has_present_or_approved_request(
        employee, later_start, before_later_half
    ):
        return True

    return False


def get_required_present_half_after_leave(leave, date):
    if not is_half_day_leave_on(leave, date):
        return None

    if half_types_match(getattr(leave, "custom_half_type", None), "First Half"):
        return "Second Half"
    return None


def get_required_present_half_before_leave(leave, date):
    if not is_half_day_leave_on(leave, date):
        return None

    if half_types_match(getattr(leave, "custom_half_type", None), "Second Half"):
        return "First Half"
    return None


def is_half_day_leave_on(leave, date):
    return (
        cint(getattr(leave, "half_day", 0))
        and getattr(leave, "half_day_date", None)
        and getdate(leave.half_day_date) == getdate(date)
    )


def has_present_or_approved_request(employee, date, required_half=None):
    if has_present_attendance(employee, date, required_half):
        return True

    return has_approved_attendance_request(employee, date, required_half)


def has_present_attendance(employee, date, required_half=None):
    attendances = frappe.get_all(
        "Attendance",
        filters={
            "employee": employee,
            "attendance_date": date,
            "status": ["in", ["Present", "Half Day"]],
            "docstatus": 1,
        },
        fields=[
            "status",
            "custom_half_type",
            "leave_application",
            "attendance_request",
            "shift",
            "attendance_date",
            "in_time",
            "out_time",
            "custom_attendance_tag",
        ],
        limit=10,
    )

    for attendance in attendances:
        if attendance.status == "Present":
            present_half = "Full Day" if is_attendance_evidence_backed(attendance) else None
        else:
            present_half = get_present_half_from_attendance(attendance)

        if not present_half:
            continue
        if not required_half:
            return True
        if present_half == "Full Day" or half_types_match(present_half, required_half):
            return True

    return False


_GENUINE_PRESENCE_TAGS = {"P", "POW", "POH"}


def is_attendance_evidence_backed(attendance):
    # No-punch / single-checkin employees use custom_attendance_tag instead of bio-times.
    # "P" = regular workday, "POW"/"POH" = worked on WO/holiday. "WO"/"HO" must be excluded.
    if getattr(attendance, "custom_attendance_tag", None) in _GENUINE_PRESENCE_TAGS:
        return True
    if attendance.shift and attendance.in_time and attendance.out_time:
        return True
    if attendance.attendance_request:
        return True
    return False


def get_present_half_from_attendance(attendance):
    if attendance.leave_application:
        leave_half = attendance.custom_half_type or frappe.db.get_value(
            "Leave Application", attendance.leave_application, "custom_half_type"
        )
        return get_opposite_half(leave_half)

    if attendance.attendance_request:
        return frappe.db.get_value(
            "Attendance Request", attendance.attendance_request, "custom_half_type"
        )

    return infer_present_half_from_attendance(attendance)


def infer_present_half_from_attendance(attendance):
    if not (attendance.shift and attendance.in_time and attendance.out_time):
        return None

    shift = frappe.db.get_value(
        "Shift Type", attendance.shift, ["start_time", "end_time"], as_dict=True
    )
    if not (shift and shift.start_time and shift.end_time):
        return None

    attendance_date = getdate(attendance.attendance_date)
    shift_start = get_datetime(attendance_date) + get_timedelta(shift.start_time)
    shift_end = get_datetime(attendance_date) + get_timedelta(shift.end_time)
    if shift_end <= shift_start:
        shift_end = shift_end + timedelta(days=1)

    midpoint = shift_start + ((shift_end - shift_start) / 2)
    in_time = get_datetime(attendance.in_time)
    out_time = get_datetime(attendance.out_time)

    if in_time >= midpoint:
        return "Second Half"
    if out_time <= midpoint:
        return "First Half"

    first_overlap = max(
        0, (min(out_time, midpoint) - max(in_time, shift_start)).total_seconds()
    )
    second_overlap = max(
        0, (min(out_time, shift_end) - max(in_time, midpoint)).total_seconds()
    )
    if first_overlap > second_overlap:
        return "First Half"
    if second_overlap > first_overlap:
        return "Second Half"
    return None


def has_approved_attendance_request(employee, date, required_half=None):
    requests = frappe.get_all(
        "Attendance Request",
        filters={
            "employee": employee,
            "from_date": ["<=", date],
            "to_date": [">=", date],
            "docstatus": 1,
            "workflow_state": "Approved",
        },
        fields=["half_day", "half_day_date", "custom_half_type"],
        limit=10,
    )

    for request in requests:
        if not cint(request.half_day):
            return True
        if getdate(request.half_day_date) != getdate(date):
            continue
        if not required_half:
            return True
        if half_types_match(request.custom_half_type, required_half):
            return True

    return False


def get_opposite_half(half_type):
    half_type = normalize_half_type(half_type)
    if half_type == "first half":
        return "Second Half"
    if half_type == "second half":
        return "First Half"
    return None


def validate_change_request_day(doc):
    roles = frappe.get_roles()
    if (
        "HR Manager" in roles
        or "HR User" in roles
        or any("Payroll" in r for r in roles)
    ):
        return
    branch = frappe.get_value("Employee", doc.employee, "branch")
    allowed_days = frappe.get_value("Branch", branch, "custom_change_request")
    if not allowed_days:
        return

    diff = date_diff(getdate(), doc.from_date)
    if diff > allowed_days:
        frappe.throw(
            frappe._("You can only change attendance request within {0} days.").format(
                allowed_days
            )
        )


def format_display_date(value):
    if not value:
        return ""
    return formatdate(value, "dd-MM-yyyy")


def validate_attendance_request(doc):
    requests = frappe.get_all(
        "Attendance Request",
        filters={
            "employee": doc.employee,
            "from_date": ["<=", doc.to_date],
            "to_date": [">=", doc.from_date],
            "docstatus": ["!=", 2],
            "workflow_state": [
                "not in",
                [
                    "Rejected",
                    "Cancelled",
                    "Reject by HOD",
                    "Reject by HR",
                    "Reject at Gate",
                ],
            ],
        },
        fields=[
            "name",
            "from_date",
            "to_date",
            "half_day_date",
            "custom_half_type",
            "half_day",
        ],
    )

    if requests:
        for r in requests:
            # Full-day attendance exists
            if not r.half_day:
                frappe.throw(
                    _(
                        "Attendance Request {0} exists for the selected date range. Cannot apply leave."
                    ).format(get_link_to_form("Attendance Request", r.name))
                )

            # Half-day attendance exists
            if r.half_day:
                # Half-day conflict
                if (
                    r.half_day_date
                    and doc.half_day_date
                    and getdate(r.half_day_date) == getdate(doc.half_day_date)
                    and r.custom_half_type == doc.custom_half_type
                ):
                    frappe.throw(
                        _(
                            "Attendance Request {0} exists for the selected half day. Cannot apply leave."
                        ).format(get_link_to_form("Attendance Request", r.name))
                    )

                # Full-day leave conflicts with existing half-day attendance
                if not getattr(doc, "half_day", False) and r.half_day_date:
                    if (
                        getdate(doc.from_date)
                        <= getdate(r.half_day_date)
                        <= getdate(doc.to_date)
                    ):
                        frappe.throw(
                            _(
                                "Attendance Request {0} already exists for a half day within this range. Full-day leave cannot be applied."
                            ).format(get_link_to_form("Attendance Request", r.name))
                        )


def validate_leave_overlap(self):
    # 1. Prepare to fetch overlapping requests
    if not self.name:
        self.name = "New Leave Application"

    requests = frappe.get_all(
        "Leave Application",
        filters={
            "employee": self.employee,
            "from_date": ["<=", self.to_date],
            "to_date": [">=", self.from_date],
            "docstatus": ["!=", 2],
            "workflow_state": [
                "not in",
                ["Cancelled", "Rejected by HOD", "Rejected by HR"],
            ],
            "name": ["!=", self.name],
        },
        fields=[
            "name",
            "from_date",
            "to_date",
            "half_day_date",
            "custom_half_type",
            "half_day",
            "leave_type",
        ],
    )

    if requests:
        for r in requests:
            if not cint(r.half_day):
                self.throw_overlap_error(r)

            elif cint(r.half_day):
                is_same_date = (
                    r.half_day_date
                    and self.half_day_date
                    and getdate(r.half_day_date) == getdate(self.half_day_date)
                )

                if is_same_date and r.custom_half_type == self.custom_half_type:
                    self.throw_overlap_error(r)

                elif is_same_date and r.custom_half_type != self.custom_half_type:
                    continue

                if not cint(self.half_day) and r.half_day_date:
                    if (
                        getdate(self.from_date)
                        <= getdate(r.half_day_date)
                        <= getdate(self.to_date)
                    ):
                        self.throw_overlap_error(r)


def throw_overlap_error(self, d):
    # Use the existing error function from Leave Application Doctype
    form_link = get_link_to_form("Leave Application", d.name)
    msg = _(
        "Employee {0} has already applied for {1} between {2} and {3} : {4}"
    ).format(
        self.employee,
        d["leave_type"],
        formatdate(d["from_date"]),
        formatdate(d["to_date"]),
        form_link,
    )
    frappe.throw(msg, OverlapError)


def has_present_day_between(employee, start_date, end_date):
    """
    Returns True if employee has at least one Attendance
    with status = 'Present' between start_date and end_date (exclusive).
    """
    start_date = getdate(start_date)
    end_date = getdate(end_date)
    _filter_dates = []
    current_date = add_days(start_date, 1)

    while current_date < end_date:
        if is_holiday_for_employee(employee, current_date):
            current_date = add_days(current_date, 1)
            continue
        _filter_dates.append(current_date)
        current_date = add_days(current_date, 1)

    if not _filter_dates:
        return False

    return bool(
        frappe.db.exists(
            "Attendance",
            {
                "employee": employee,
                "attendance_date": ["in", _filter_dates],
                "status": ["in", ["Present", "Half Day"]],
                "leave_application": ["is", "not set"],
                "docstatus": 1,
            },
        )
    )


def validate_leave_balance(doc):
    previous = None if doc.is_new() else doc.get_doc_before_save()
    is_draft_apply_flow = doc.docstatus == 0 and doc.status == "Open"
    is_hod_to_hr = (
        previous
        and previous.docstatus == 0
        and previous.workflow_state != doc.workflow_state
        and previous.workflow_state == "Pending at HOD"
        and doc.workflow_state == "Pending at HR"
    )
    is_hr_final_approval = (
        previous
        and previous.workflow_state != doc.workflow_state
        and previous.workflow_state == "Pending at HR"
        and doc.workflow_state == "Approved"
    )

    # Enforce this check while the employee is applying in draft/open flow,
    # and again on the final HR approval. Skip it on the HOD handoff step.
    if not is_draft_apply_flow and not is_hr_final_approval:
        return

    if is_hod_to_hr:
        return

    if frappe.db.get_value("Leave Type", doc.leave_type, "allow_negative"):
        return

    leave_details = frappe.call(
        "hrms.hr.doctype.leave_application.leave_application.get_leave_details",
        employee=doc.employee,
        date=doc.from_date,
    )
    if leave_details and "leave_allocation" in leave_details:
        leave_allocation = leave_details["leave_allocation"]
        if doc.leave_type in ["Leave Without Pay", "Auto Leave Without Pay"]:
            return
        if doc.leave_type not in leave_allocation:
            return
        pending = leave_allocation[doc.leave_type]["leaves_pending_approval"] or 0

        if is_hr_final_approval:
            # At final HR approval, reserve balance only for earlier pending leave dates.
            earlier_pending = frappe.get_all(
                "Leave Application",
                filters={
                    "employee": doc.employee,
                    "leave_type": doc.leave_type,
                    "status": "Open",
                    "docstatus": 0,
                    "name": ["!=", doc.name],
                    "from_date": ["<", doc.from_date],
                },
                fields=["SUM(total_leave_days) as leaves"],
            )
            pending = (earlier_pending[0].get("leaves") or 0) if earlier_pending else 0
        elif not doc.is_new():
            # Avoid double counting this same document when it already exists in Open state.
            existing = frappe.db.get_value(
                "Leave Application",
                doc.name,
                ["docstatus", "status", "total_leave_days"],
                as_dict=True,
            )
            if existing and existing.docstatus == 0 and existing.status == "Open":
                pending = max(0, pending - (existing.total_leave_days or 0))

        remaining = leave_allocation[doc.leave_type]["remaining_leaves"]
        total_available = remaining - pending
        if doc.total_leave_days <= total_available:
            return

        emp_grade = frappe.db.get_value("Employee", doc.employee, "grade")
        advance_leave = (
            frappe.db.get_value(
                "Employee Grade",
                emp_grade,
                [
                    "custom_allow_advance_leave",
                    "custom_max_no_of_advance_debit",
                    "custom_leave_type",
                ],
                as_dict=True,
            )
            if emp_grade
            else None
        )

        if (
            advance_leave
            and advance_leave.custom_allow_advance_leave
            and advance_leave.custom_leave_type == doc.leave_type
            and abs(advance_leave.custom_max_no_of_advance_debit or 0)
        ):
            projected_balance = total_available - (doc.total_leave_days or 0)
            if projected_balance >= -abs(advance_leave.custom_max_no_of_advance_debit):
                return

            frappe.throw(
                _(
                    "Insufficient leave balance for {0}, You have reached maximum allowed advance leave"
                ).format(doc.leave_type)
            )

        frappe.throw(_("Insufficient leave balance for {0}").format(doc.leave_type))


class OverlapError(frappe.ValidationError):
    pass


class SandwichPolicyError(frappe.ValidationError):
    pass
