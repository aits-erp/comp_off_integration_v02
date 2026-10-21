import frappe
from frappe import _
from frappe.utils import date_diff, get_datetime, get_first_day, get_last_day, get_link_to_form, getdate


MIS_PUNCH_LIMIT_REACHED_MESSAGE = "Mis Punch application limit reached for this month."
MIS_PUNCH_VALID_PAIR_EXISTS_MESSAGE = (
    "Mis Punch request cannot be created when both check-in and check-out are available for the selected date."
)
MIS_PUNCH_NO_CHECKIN_EXISTS_MESSAGE = (
    "Mis Punch request cannot be created when no check-in or check-out is available for the selected date. "
    "Please apply Official attendance request."
)
REJECTED_ATTENDANCE_REQUEST_STATES = (
    "Rejected by HOD",
    "Rejected at Gate",
    "Rejected by HR",
)
INACTIVE_OVERLAP_STATES = (
    "Rejected",
    "Cancelled",
    "Reject by HOD",
    "Reject by HR",
    "Reject at Gate",
    *REJECTED_ATTENDANCE_REQUEST_STATES,
)


def validate(doc, method=None):
    if is_salary_processed(doc):
        frappe.throw(
            frappe._(
                "Attendance Request cannot be created, updated, or approved because a Salary Slip already exists for this period."
            )
        )

    validate_zero_punch_employee(doc)
    validate_change_request_day(doc)
    validate_workflow_state(doc)
    validate_date(doc)
    validate_attendance(doc)

    if doc.reason == "Mis Punch":
        if getdate(doc.from_date) != getdate(doc.to_date):
            frappe.throw(frappe._("Attendance Request for Mis Punch can be marked for single day only!!"))
        validate_mis_punch_checkins(doc)
        validate_mis_punch_monthly_limit(doc)


def before_cancel(doc, method=None):
    if is_salary_processed(doc):
        frappe.throw(
            frappe._("Cannot cancel: a Salary Slip (draft or submitted) already exists for this period."),
            SandwichPolicyError,
        )


def before_delete(doc, method=None):
    if is_salary_processed(doc):
        frappe.throw(
            frappe._("Cannot delete: a Salary Slip (draft or submitted) already exists for this period.")
        )


def on_submit(doc, method=None):
    doc.status = "Approved"


def on_cancel(doc, method=None):
    doc.status = "Cancelled"


def validate_workflow_state(doc):
    if doc.workflow_state in (
        "Rejected by HOD",
        "Rejected by HR",
        "Rejected at Gate",
    ) and not (doc.custom_reason_for_rejection or "").strip():
        frappe.throw(frappe._("Kindly set the reason for rejection"))


def validate_zero_punch_employee(doc):
    grade = frappe.get_value("Employee", doc.employee, "grade")
    is_zero_punch = frappe.get_value("Employee Grade", grade, "custom_no_punch_applicable")
    if is_zero_punch:
        frappe.throw(frappe._("Attendance Request cannot be created for Zero Punch Employee"))


def cancel_short_leaves(doc):
    attendance = frappe.db.exists(
        "Attendance",
        {
            "date": ["between", [doc.from_date, doc.to_date]],
            "employee": doc.employee,
            "status": ["in", ["Present", "Absent", "Half Day"]],
        },
    )
    if attendance:
        frappe.throw(frappe._("Attendance is already marked for the selected dates."))
    else:
        short_leaves = frappe.get_all(
            "Short Leave",
            filters={
                "employee": doc.employee,
                "for_date": ["between", [doc.from_date, doc.to_date]],
                "docstatus": 1,
            },
            pluck="name",
        )
        for sl in short_leaves:
            sl_doc = frappe.get_doc("Short Leave", sl)
            sl_doc.cancel()


def validate_date(doc):
    leaves = frappe.get_all(
        "Leave Application",
        filters={
            "employee": doc.employee,
            "from_date": ["<=", doc.to_date],
            "to_date": [">=", doc.from_date],
            "docstatus": ["!=", 2],
            "workflow_state": ["not in", INACTIVE_OVERLAP_STATES],
        },
        fields=["docstatus", "name", "half_day_date", "custom_half_type", "half_day", "from_date", "to_date"],
    )

    if leaves:
        for l in leaves:
            if not l.half_day:
                frappe.throw(
                    _(
                        "Leave Application {0} exists for the selected date range. Attendance Request cannot be processed."
                    ).format(get_link_to_form("Leave Application", l.name))
                )

            if l.half_day:
                if (
                    l.half_day_date
                    and doc.half_day_date
                    and getdate(l.half_day_date) == getdate(doc.half_day_date)
                    and l.custom_half_type == doc.custom_half_type
                ):
                    frappe.throw(
                        _(
                            "Leave Application {0} exists for the selected half day. Attendance Request cannot be processed."
                        ).format(get_link_to_form("Leave Application", l.name))
                    )

                if not getattr(doc, "half_day", False) and l.half_day_date:
                    if getdate(doc.from_date) <= getdate(l.half_day_date) <= getdate(doc.to_date):
                        frappe.throw(
                            _(
                                "Leave Application {0} already exists for a half day within this date range. Full-day Attendance Request cannot be processed."
                            ).format(get_link_to_form("Leave Application", l.name))
                        )

    requests = frappe.get_all( 
        "Attendance Request",
        filters={
            "employee": doc.employee,
            "from_date": ["<=", doc.to_date],
            "to_date": [">=", doc.from_date],
            "docstatus": ["!=", 2],
            "name": ["!=", doc.name],
            "workflow_state": ["not in", INACTIVE_OVERLAP_STATES],
        },
        fields=["name", "from_date", "to_date", "half_day_date", "custom_half_type", "half_day"],
    )

    if requests:
        for r in requests:
            if not r.half_day:
                frappe.throw(
                    _(
                        "Attendance Request {0} exists for the selected date range. Attendance Request cannot be processed."
                    ).format(get_link_to_form("Attendance Request", r.name))
                )

            if r.half_day:
                if (
                    r.half_day_date
                    and doc.half_day_date
                    and getdate(r.half_day_date) == getdate(doc.half_day_date)
                    and r.custom_half_type == doc.custom_half_type
                ):
                    frappe.throw(
                        _(
                            "Attendance Request {0} exists for the selected half day. Attendance Request cannot be processed."
                        ).format(get_link_to_form("Attendance Request", r.name))
                    )
                if not getattr(doc, "half_day", False) and r.half_day_date:
                    if getdate(doc.from_date) <= getdate(r.half_day_date) <= getdate(doc.to_date):
                        frappe.throw(
                            _(
                                "Attendance Request {0} already exists for a half day within this date range. Full-day Attendance Request cannot be processed."
                            ).format(get_link_to_form("Attendance Request", r.name))
                        )


def validate_attendance(doc):
    if frappe.flags.in_reprocess_attendance:
        return
    if frappe.db.exists(
        "Attendance",
        {
            "employee": doc.employee,
            "attendance_date": ["between", [doc.from_date, doc.to_date]],
            "status": "Present",
            "docstatus": ["!=", 2],
        },
    ):
        frappe.throw(frappe._("Attendance is already marked for the Employee {0}").format(doc.employee))


def validate_change_request_day(doc):
    roles = frappe.get_roles()
    if "HR Manager" in roles or "HR User" in roles or any("Payroll" in r for r in roles):
        return
    branch = frappe.get_value("Employee", doc.employee, "branch")
    allowed_days = frappe.get_value("Branch", branch, "custom_change_request")
    if not allowed_days:
        return

    diff = date_diff(getdate(), doc.from_date)
    if diff > allowed_days:
        frappe.throw(frappe._("You can only change attendance request within {0} days.").format(allowed_days))


def validate_mis_punch_monthly_limit(doc):
    allowed_mis_punch_days = get_allowed_mis_punch_days(doc.employee)
    if not allowed_mis_punch_days:
        return

    request_date = getdate(doc.from_date)
    existing_mis_punch_requests = get_monthly_mis_punch_request_count(
        doc.employee,
        request_date,
        doc.name,
    )

    if existing_mis_punch_requests >= allowed_mis_punch_days:
        frappe.throw(frappe._(MIS_PUNCH_LIMIT_REACHED_MESSAGE))


def validate_mis_punch_checkins(doc):
    has_in, has_out = get_mis_punch_checkin_flags(
        doc.employee,
        getdate(doc.from_date),
        getattr(doc, "shift", None),
    )

    if has_in and has_out:
        frappe.throw(frappe._(MIS_PUNCH_VALID_PAIR_EXISTS_MESSAGE))

    if not has_in and not has_out:
        frappe.throw(frappe._(MIS_PUNCH_NO_CHECKIN_EXISTS_MESSAGE))


def get_mis_punch_checkin_flags(employee, request_date, shift=None):
    log_types = {
        get_checkin_log_type(checkin)
        for checkin in get_mis_punch_checkins(employee, request_date, shift)
    }

    return "IN" in log_types, "OUT" in log_types


def get_mis_punch_checkins(employee, request_date, shift=None):
    day_start = get_datetime(f"{request_date} 00:00:00")
    day_end = get_datetime(f"{request_date} 23:59:59")
    filters = {
        "employee": employee,
        "shift_start": ["between", [day_start, day_end]],
    }

    if shift:
        filters["shift"] = shift

    return frappe.get_all(
        "Employee Checkin",
        filters=filters,
        fields=["time", "log_type", "shift_start"],
        order_by="time asc",
    )


def get_checkin_log_type(checkin):
    return (get_checkin_value(checkin, "log_type") or "").upper()


def get_checkin_value(checkin, fieldname):
    if isinstance(checkin, dict):
        return checkin.get(fieldname)

    return getattr(checkin, fieldname, None)


def get_allowed_mis_punch_days(employee):
    branch = frappe.get_value("Employee", employee, "branch")
    if not branch:
        return 0

    return frappe.get_value("Branch", branch, "custom_allowed_mis_punch_days") or 0


def get_monthly_mis_punch_request_count(employee, request_date, current_request=None):
    month_start = get_first_day(request_date)
    month_end = get_last_day(request_date)
    rejected_states = ", ".join(["%s"] * len(REJECTED_ATTENDANCE_REQUEST_STATES))

    return frappe.db.sql(
        f"""
        SELECT COUNT(name)
        FROM `tabAttendance Request`
        WHERE employee = %s
            AND reason = 'Mis Punch'
            AND docstatus != 2
            AND name != %s
            AND from_date BETWEEN %s AND %s
            AND (
                workflow_state IS NULL
                OR workflow_state = ''
                OR workflow_state NOT IN ({rejected_states})
            )
        """,
        (
            employee,
            current_request or "",
            month_start,
            month_end,
            *REJECTED_ATTENDANCE_REQUEST_STATES,
        ),
    )[0][0]


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

class SandwichPolicyError(frappe.ValidationError):
    pass
