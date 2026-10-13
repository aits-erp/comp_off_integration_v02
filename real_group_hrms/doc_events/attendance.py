from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import (
    add_days,
    date_diff,
    get_datetime,
    get_first_day,
    get_last_day,
    getdate,
)

from real_group_hrms.helper.attendance_helper import create_attendance
from real_group_hrms.utils import (
    convert_time_to_hours,
    get_weekly_off_based_on_date,
    half_types_differ,
    is_holiday_for_employee,
)


def validate(doc, method=None):
    if is_salary_processed(doc):
        frappe.throw(
            _(
                "Attendance cannot be created or updated because a Salary Slip already exists for this date."
            )
        )

    if doc.working_hours is not None and doc.working_hours < 0:
        frappe.throw(_("Working hours cannot be negative."))

    doc.custom_working_hours = None
    if doc.working_hours and doc.working_hours > 0:
        total_seconds = round(doc.working_hours * 3600 / 60) * 60
        # Time fields cannot store 24h+ durations; keep the numeric hours and leave the display field empty.
        if total_seconds < 24 * 60 * 60:
            doc.custom_working_hours = timedelta(seconds=total_seconds)
    else:
        doc.custom_working_hours = None


def before_cancel(doc, method=None):
    if is_salary_processed(doc):
        frappe.throw(
            frappe._(
                "Attendance change not allowed since salary slip is created for the period."
            ),
            SandwichPolicyError,
        )


def on_cancel(doc, method=None):
    cancel_incentive_or_c_off(
        doc,
        cancel_incentive=not getattr(
            frappe.flags, "in_leave_application_attendance_sync", False
        ),
    )


def before_delete(doc, method=None):
    if is_salary_processed(doc):
        frappe.throw(
            frappe._("Cannot delete: a Salary Slip already exists for this period.")
        )


def on_submit(doc, method=None):
    update_attendance_status(doc)
    update_attendance_tag(doc)
    if frappe.flags.in_reprocess_attendance:
        return
    if doc.custom_marked_absent_by_sandwich:
        return
    # Leave approval and leave-cancellation rebuilds may retain the employee's
    # recorded work hours. They must not turn that attendance maintenance into
    # a fresh extra-work incentive allocation.
    if not (
        doc.leave_application
        or getattr(frappe.flags, "in_leave_application_attendance_sync", False)
    ):
        frappe.enqueue(
            allocate_incentive, doc=doc, queue="long", enqueue_after_commit=True
        )
    frappe.enqueue(allocate_c_off, doc=doc, queue="long", enqueue_after_commit=True)

    # Any absence-side status can bracket a Weekly-Off/Holiday and trigger a
    # sandwich mark - not just "Absent". A full-day leave ("On Leave") or a
    # leave-driven Half Day is equally an absence for sandwich purposes, so
    # gate on the same predicate the sandwich helpers use internally.
    if is_absence_side_status(
        doc.status, doc.leave_application, doc.attendance_request
    ):
        frappe.enqueue(
            sandwich_attendance, doc=doc, queue="long", enqueue_after_commit=True
        )
    else:
        frappe.enqueue(
            revert_sandwich_attendance, doc=doc, queue="long", enqueue_after_commit=True
        )


def get_reprocess_reference(doc):
    return getattr(frappe.flags, "reprocess_attendance_reference", None) or getattr(
        doc, "custom_reprocess_reference", None
    )


def set_doc_reprocess_reference(doc, reprocess_reference):
    if reprocess_reference and doc.meta.has_field("custom_reprocess_reference"):
        doc.db_set("custom_reprocess_reference", reprocess_reference)


def is_salary_processed(doc):
    if not (doc.employee and doc.attendance_date):
        return False

    return frappe.db.exists(
        "Salary Slip",
        {
            "employee": doc.employee,
            "start_date": ["<=", doc.attendance_date],
            "end_date": [">=", doc.attendance_date],
            "docstatus": ["!=", 2],
        },
    )


def cancel_incentive_or_c_off(doc, cancel_incentive=True):
    reprocess_reference = get_reprocess_reference(doc)
    c_offs = frappe.db.get_all(
        "Compensatory Leave Request",
        filters={
            "employee": doc.employee,
            "work_from_date": doc.attendance_date,
            "work_end_date": doc.attendance_date,
            "docstatus": 1,
        },
    )
    for c_off in c_offs:
        c_off_doc = frappe.get_doc("Compensatory Leave Request", c_off.name)
        set_doc_reprocess_reference(c_off_doc, reprocess_reference)
        c_off_doc.cancel()

    if not cancel_incentive:
        return

    incentive_logs = frappe.db.get_all(
        "Incentive Log",
        filters={
            "employee": doc.employee,
            "work_date": doc.attendance_date,
            "docstatus": 1,
        },
    )
    for incentive_log in incentive_logs:
        incentive_log_doc = frappe.get_doc("Incentive Log", incentive_log.name)
        set_doc_reprocess_reference(incentive_log_doc, reprocess_reference)
        # incentive_log_doc.cancel()
        additional_salary = frappe.db.get_value(
            "Additional Salary",
            {
                "employee": doc.employee,
                "custom_incentive_reference": incentive_log_doc.name,
                "docstatus": 1,
            },
        )
        if additional_salary:
            additional_salary_doc = frappe.get_doc(
                "Additional Salary", additional_salary
            )
            additional_salary_doc.cancel()
        incentive_log_doc.cancel()


def update_attendance_status(doc):
    if (
        doc.attendance_request
        and not doc.leave_application
        and doc.status == "Half Day"
    ):
        is_holiday = is_holiday_for_employee(doc.employee, doc.attendance_date)
        if is_holiday and is_holiday.get("is_half_day"):
            request_half_day_date = frappe.get_value(
                "Attendance Request", doc.attendance_request, "half_day_date"
            )
            request_half_type = frappe.get_value(
                "Attendance Request", doc.attendance_request, "custom_half_type"
            )
            request_reason = frappe.get_value(
                "Attendance Request", doc.attendance_request, "reason"
            )
            if (
                request_half_day_date
                and getdate(request_half_day_date) == getdate(doc.attendance_date)
                and (
                    half_types_differ(is_holiday.get("half_type"), request_half_type)
                    or not request_half_type
                )
            ):
                doc.status = "Half Day" if request_reason == "Mis Punch" else "Present"
                frappe.db.set_value("Attendance", doc.name, "status", doc.status)

    if doc.leave_application and doc.status == "Half Day":
        is_holiday = is_holiday_for_employee(doc.employee, doc.attendance_date)
        is_lwp = frappe.get_value("Leave Type", doc.leave_type, "is_lwp")
        if is_holiday and is_holiday.get("is_half_day"):
            leave_half_type = frappe.get_value(
                "Leave Application", doc.leave_application, "custom_half_type"
            )
            if (
                half_types_differ(is_holiday.get("half_type"), leave_half_type)
                or not leave_half_type
            ):
                if is_lwp:
                    doc.status = "Absent"
                else:
                    doc.status = "Present"
                frappe.db.set_value("Attendance", doc.name, "status", doc.status)

        if doc.attendance_request:
            request_half_day_date = frappe.get_value(
                "Attendance Request", doc.attendance_request, "half_day_date"
            )
            leave_half_date = frappe.get_value(
                "Leave Application", doc.leave_application, "half_day_date"
            )
            request_half_type = frappe.get_value(
                "Attendance Request", doc.attendance_request, "custom_half_type"
            )
            leave_half_type = frappe.get_value(
                "Leave Application", doc.leave_application, "custom_half_type"
            )
            if (
                request_half_day_date
                and leave_half_date
                and getdate(request_half_day_date) == getdate(leave_half_date)
                and (
                    half_types_differ(request_half_type, leave_half_type)
                    or not request_half_type
                    or not leave_half_type
                )
            ):
                if not is_lwp:
                    doc.status = "Present"

        frappe.db.set_value("Attendance", doc.name, "status", doc.status)


def get_leave_code_for_tag(leave_type_doc):
    if not leave_type_doc:
        return None

    if leave_type_doc.is_lwp:
        return "LW"

    leave_name = (leave_type_doc.name or "").lower()
    if "earned leave" in leave_name:
        return "EL"
    if "casual leave" in leave_name:
        return "CL"
    if leave_type_doc.is_compensatory:
        return "CO"

    return None


def get_half_day_holiday_combo_tag(doc, holiday):
    if not holiday or not holiday.get("is_holiday") or not holiday.get("is_half_day"):
        return None

    holiday_half_type = holiday.get("half_type")

    if doc.leave_application and doc.leave_type:
        leave_half_type = frappe.get_cached_value(
            "Leave Application", doc.leave_application, "custom_half_type"
        )
        if half_types_differ(holiday_half_type, leave_half_type):
            leave_type = frappe.get_cached_doc("Leave Type", doc.leave_type)
            leave_code = get_leave_code_for_tag(leave_type)
            return {
                "EL": "ELHO",
                "CL": "CLHO",
                "CO": "COHO",
                "LW": "LWHO",
            }.get(leave_code)

    if doc.attendance_request:
        request = frappe.get_cached_doc("Attendance Request", doc.attendance_request)
        if (
            getattr(request, "half_day", False)
            and getattr(request, "half_day_date", None)
            and getdate(request.half_day_date) == getdate(doc.attendance_date)
            and half_types_differ(
                holiday_half_type, getattr(request, "custom_half_type", None)
            )
        ):
            if request.reason == "Mis Punch":
                return "PHO"
            return "ODHO"

    if doc.status == "Present":
        return "PHO"

    if doc.status == "Half Day":
        return "HHO"

    return None


def get_attendance_checkin_log_types(doc):
    log_types = frappe.get_all(
        "Employee Checkin", filters={"attendance": doc.name}, pluck="log_type"
    )
    if log_types:
        return [log_type for log_type in log_types if log_type]

    attendance_date = getattr(doc, "attendance_date", None)
    employee = getattr(doc, "employee", None)
    if not attendance_date or not employee:
        return []

    start = get_datetime(getdate(attendance_date))
    end = get_datetime(add_days(getdate(attendance_date), 1))
    fallback_filters = [
        ["employee", "=", employee],
        ["shift_start", ">=", start],
        ["shift_start", "<", end],
    ]
    log_types = frappe.get_all(
        "Employee Checkin", filters=fallback_filters, pluck="log_type"
    )
    if log_types:
        return [log_type for log_type in log_types if log_type]

    fallback_filters = [
        ["employee", "=", employee],
        ["time", ">=", start],
        ["time", "<", end],
    ]
    log_types = frappe.get_all(
        "Employee Checkin", filters=fallback_filters, pluck="log_type"
    )
    return [log_type for log_type in log_types if log_type]


def has_attendance_checkins(doc):
    return bool(get_attendance_checkin_log_types(doc))


def has_valid_holiday_in_out_pair(doc):
    log_types = get_attendance_checkin_log_types(doc)
    if not log_types:
        return False
    return "IN" in log_types and "OUT" in log_types


def update_attendance_tag(doc):
    status = ""

    is_holiday = is_holiday_for_employee(doc.employee, doc.attendance_date)
    grade = frappe.get_value("Employee", doc.employee, "grade")
    is_sandwich = frappe.db.get_value("Employee Grade", grade, "custom_sandwich_flag")
    half_day_holiday_combo = get_half_day_holiday_combo_tag(doc, is_holiday)
    if half_day_holiday_combo:
        status = half_day_holiday_combo
    elif doc.status == "On Leave" or doc.leave_application:
        leave_type = frappe.get_doc("Leave Type", doc.leave_type)
        if (
            is_sandwich
            and is_holiday
            and is_holiday.get("is_holiday")
            and not is_holiday.get("is_half_day")
        ):
            if doc.leave_application:
                if "earned leave" in leave_type.name.lower():
                    status = "EL"
                elif "casual leave" in leave_type.name.lower():
                    status = "CL"
                elif leave_type.is_compensatory:
                    status = "CO"
                else:
                    status = "A"
            else:
                status = "A"
        elif leave_type.is_lwp:
            status = "LWP"
        elif "earned leave" in leave_type.name.lower():
            status = "EL"
        elif "casual leave" in leave_type.name.lower():
            status = "CL"
        elif leave_type.is_compensatory:
            status = "CO"

    elif doc.status == "Present" and not is_holiday:
        status = "P"
    elif doc.status == "Half Day":
        if is_holiday and is_holiday.get("is_holiday"):
            if is_holiday.get("is_weekly_off"):
                status = "WO"
            else:
                status = "HO"
        else:
            status = "HD"
    elif doc.status == "Absent":
        status = "A"
    elif is_holiday and is_holiday.get("is_holiday"):
        if has_valid_holiday_in_out_pair(doc):
            if is_holiday.get("is_weekly_off"):
                status = "POW"
            else:
                status = "POH"
        else:
            if is_holiday.get("is_weekly_off"):
                status = "WO"
            else:
                status = "HO"

    frappe.db.set_value("Attendance", doc.name, "custom_attendance_tag", status)

    if status == "Half Day" and doc.leave_application:
        half_day_date = frappe.db.get_value(
            "Leave Application", doc.leave_application, "half_day_date"
        )
        if half_day_date and getdate(half_day_date) == getdate(doc.attendance_date):
            half_type = frappe.db.get_value(
                "Leave Application", doc.leave_application, "custom_half_type"
            )
            frappe.db.set_value("Attendance", doc.name, "custom_half_type", half_type)


def get_cross_day_incentive_replacement_action(doc, total_credit):
    """Return whether a cross-day completion replaces same-work-date logs.

    A regular shift may earn an initial incentive before the following
    cross-day shift has completed. When that cross-day shift is linked to the
    same Attendance, the matrix result is the final entitlement for the work
    date, so the earlier partial log must be replaced rather than added to.
    """
    linked_shifts = frappe.get_all(
        "Employee Checkin",
        filters={"attendance": doc.name},
        pluck="shift",
    )
    if not any(
        shift and frappe.get_cached_value("Shift Type", shift, "custom_is_cross_day")
        for shift in linked_shifts
    ):
        return None, []

    existing_logs = frappe.get_all(
        "Incentive Log",
        filters={
            "employee": doc.employee,
            "work_date": doc.attendance_date,
            "docstatus": 1,
        },
        fields=["name", "credit"],
    )
    existing_credit = sum((log.get("credit") or 0) for log in existing_logs)

    if not existing_logs:
        return "create", []
    if existing_credit < total_credit:
        return "replace", existing_logs
    return "skip", existing_logs


def allocate_incentive(doc):
    reprocess_reference = get_reprocess_reference(doc)

    def _create_additional_salary(employee: str, amount, incentive_log_name):
        new_additional_salary = frappe.get_doc(
            dict(
                doctype="Additional Salary",
                employee=employee,
                payroll_date=get_last_day(doc.attendance_date),
                salary_component="Incentives",
                amount=amount,
                custom_incentive_reference=incentive_log_name,
                custom_reprocess_reference=reprocess_reference,
                overwrite_salary_structure_amount=0,
            )
        )
        new_additional_salary.insert(ignore_permissions=True)
        new_additional_salary.submit()

    def _create_incentive_log(
        employee: str,
        amount,
        from_date,
        to_date,
        work_date,
        status,
        hours_worked,
        credit,
    ):
        incentive_log = frappe.get_doc(
            dict(
                doctype="Incentive Log",
                employee=employee,
                from_date=from_date,
                to_date=to_date,
                incentive=amount,
                work_date=work_date,
                status=status,
                credit=credit,
                extra_worked_hours=hours_worked,
                custom_reprocess_reference=reprocess_reference,
            )
        )
        incentive_log.insert(ignore_permissions=True)
        incentive_log.submit()
        return incentive_log

    def round_incentive(amount):
        remainder = amount % 50
        if remainder <= 25:
            return amount - remainder
        return amount + (50 - remainder)

    employee = frappe.get_cached_doc("Employee", doc.employee, for_update=False)
    date_of_joining = employee.date_of_joining

    # Do we even need this check? Attendance cannot be created before date of joining
    if date_of_joining and getdate(doc.attendance_date) < date_of_joining:
        return

    grade = employee.grade
    branch = employee.branch
    grade_doc = frappe.get_cached_doc("Employee Grade", grade, for_update=False)

    if (
        grade_doc.custom_present_on_holiday != "Incentive"
        and grade_doc.custom_extra_work_hour != "Incentive"
    ):
        return

    hours = doc.working_hours
    checkins = frappe.db.exists(
        "Employee Checkin", {"attendance": doc.name}, cache=True
    )
    if not hours or hours == 0:
        return
    status = ""
    holiday = is_holiday_for_employee(doc.employee, doc.attendance_date)
    if (
        holiday
        and holiday.get("is_holiday")
        and not (checkins or has_attendance_checkins(doc))
    ):
        return  # It is holiday and employee did not worked.

    if holiday and holiday.get("is_holiday") and holiday.get("is_weekly_off"):
        status = "POW"
    else:
        status = "POH"

    shift = doc.shift
    shift = frappe.get_cached_doc("Shift Type", shift) if shift else None
    if not shift:
        return

    shift_duration = convert_time_to_hours(shift.custom_shift_time)

    # if holiday and holiday.get("is_half_day") and hours <= (shift_duration / 2):
    #     return
    # if hours <= shift_duration:
    #     return

    c_matrix = frappe.db.exists(
        "Compensation Matrix",
        {"shift_duration": timedelta(hours=shift_duration), "branch": branch},
        cache=True,
    )
    if not c_matrix:
        return
    c_matrix = frappe.get_cached_doc("Compensation Matrix", c_matrix)

    if (
        holiday
        and holiday.get("is_holiday")
        and grade_doc.custom_present_on_holiday == "Incentive"
    ):
        if holiday.get("is_half_day"):
            if hours <= (shift_duration / 2):
                return
            diff = hours - (shift_duration / 2)
        else:
            diff = hours

    if not holiday and grade_doc.custom_extra_work_hour == "Incentive":
        diff = hours - shift_duration
        status = "EW"
    worked_hrs_in_delta = timedelta(hours=diff)
    matched_c_matrix = next(
        (m for m in c_matrix.items if m.from_hrs < worked_hrs_in_delta <= m.to_hrs),
        None,
    )
    if not matched_c_matrix:
        return
    credit = matched_c_matrix.c_off_credit
    if not credit:
        return

    month_start = get_first_day(doc.attendance_date)
    month_end = get_last_day(doc.attendance_date)
    existing_incentive = frappe.db.get_value(
        "Additional Salary",
        {
            "employee": employee.name,
            "salary_component": "Incentives",
            "payroll_date": ("between", (month_start, month_end)),
            "docstatus": 1,
        },
        fieldname="name",
    )
    cross_day_action, logs_to_replace = get_cross_day_incentive_replacement_action(
        doc, credit
    )
    if cross_day_action == "replace":
        savepoint_name = f"incentive_replacement_{doc.name}".replace("-", "_")
        frappe.db.savepoint(savepoint_name)
        try:
            # An Incentive Log cannot be cancelled while the monthly Additional
            # Salary still links to it. Remove that aggregate first; it is
            # rebuilt below from the remaining logs plus the fresh full credit.
            if existing_incentive:
                additional_salary = frappe.get_doc(
                    "Additional Salary", existing_incentive
                )
                additional_salary.cancel()
                additional_salary.delete()
                existing_incentive = None
            for incentive_log in logs_to_replace:
                frappe.get_doc("Incentive Log", incentive_log.name).cancel()
        except Exception:
            frappe.db.rollback(save_point=savepoint_name)
            raise
    elif cross_day_action == "skip":
        return

    salary_structure_name = frappe.db.get_value(
        "Salary Structure Assignment",
        {"employee": employee.name},
        fieldname="salary_structure",
        cache=True,
        order_by="from_date desc",  ## from_date desc
    )
    earning = (
        frappe.db.get_value(
            "Salary Structure",
            salary_structure_name,
            fieldname="total_earning",
            cache=True,
        )
        or 0
    )
    additional_incentive = (earning / (date_diff(month_end, month_start) + 1)) * credit
    existing_incentive_logs = frappe.db.get_all(
        "Incentive Log",
        filters={
            "employee": employee.name,
            "work_date": ("between", (month_start, month_end)),
            "docstatus": 1,
        },
        fields=["name", "incentive"],
    )
    existing_incentive_amount = (
        sum((log.get("incentive") or 0) for log in existing_incentive_logs)
        if existing_incentive_logs
        else 0
    )
    incentive_ceil = grade_doc.custom_incentive_ceiling
    additional_incentive_as = additional_incentive
    if existing_incentive:
        additional_salary = frappe.get_doc("Additional Salary", existing_incentive)
        additional_incentive_as = additional_incentive + existing_incentive_amount
        additional_salary.cancel()
        additional_salary.delete()
    additional_incentive_as = (
        min(additional_incentive_as, incentive_ceil)
        if incentive_ceil
        else additional_incentive_as
    )
    additional_incentive_as = round_incentive(additional_incentive_as)

    incentive_log = _create_incentive_log(
        employee.name,
        additional_incentive,
        month_start,
        month_end,
        doc.attendance_date,
        status,
        worked_hrs_in_delta,
        credit,
    )
    _create_additional_salary(
        employee.name, additional_incentive_as, incentive_log.name
    )


def allocate_c_off(doc):
    reprocess_reference = get_reprocess_reference(doc)
    employee = frappe.get_cached_doc("Employee", doc.employee, for_update=False)
    grade = employee.grade
    branch = employee.branch
    grade_doc = frappe.get_cached_doc("Employee Grade", grade, for_update=False)

    if (
        grade_doc.custom_present_on_holiday != "Comp Off"
        and grade_doc.custom_extra_work_hour != "Comp Off"
    ):
        return

    hours = doc.working_hours
    checkins = frappe.db.exists(
        "Employee Checkin", {"attendance": doc.name}, cache=True
    )
    if not hours or hours == 0:
        return

    status = ""
    holiday = is_holiday_for_employee(doc.employee, doc.attendance_date)
    if (
        holiday
        and holiday.get("is_holiday")
        and not (checkins or has_attendance_checkins(doc))
    ):
        return  # It is holiday and employee did not worked.

    if holiday and holiday.get("is_holiday") and holiday.get("is_weekly_off"):
        status = "POW"
    else:
        status = "POH"

    shift = doc.shift
    shift = frappe.get_cached_doc("Shift Type", shift) if shift else None
    if not shift:
        return

    shift_duration = convert_time_to_hours(shift.custom_shift_time)

    # if holiday and holiday.get("is_half_day") and hours <= (shift_duration / 2):
    #     return
    # if hours <= shift_duration:
    #     return
    c_matrix = frappe.db.exists(
        "Compensation Matrix",
        {"shift_duration": timedelta(hours=shift_duration), "branch": branch},
        cache=True,
    )
    if not c_matrix:
        return
    c_matrix = frappe.get_cached_doc("Compensation Matrix", c_matrix)

    if (
        holiday
        and holiday.get("is_holiday")
        and grade_doc.custom_present_on_holiday == "Comp Off"
    ):
        if holiday.get("is_half_day"):
            if hours <= (shift_duration / 2):
                return
            diff = hours - (shift_duration / 2)
        else:
            diff = hours

    if not holiday and grade_doc.custom_extra_work_hour == "Comp Off":
        diff = hours - shift_duration
        status = "EW"
    worked_hrs_in_delta = timedelta(hours=diff)

    matched_c_matrix = next(
        (m for m in c_matrix.items if m.from_hrs < worked_hrs_in_delta <= m.to_hrs),
        None,
    )
    if not matched_c_matrix:
        return

    credit = matched_c_matrix.c_off_credit
    if not credit:
        return

    existing_c_offs = frappe.get_all(
        "Compensatory Leave Request",
        {
            "employee": employee.name,
            "work_from_date": getdate(doc.attendance_date),
            "work_end_date": getdate(doc.attendance_date),
            "docstatus": 1,
        },
    )
    if existing_c_offs:
        for existing_c_off in existing_c_offs:
            existing_c_off_doc = frappe.get_doc(
                "Compensatory Leave Request", existing_c_off
            )
            set_doc_reprocess_reference(existing_c_off_doc, reprocess_reference)
            existing_c_off_doc.cancel()

    comp_off = frappe.get_doc(
        {
            "doctype": "Compensatory Leave Request",
            "employee": employee.name,
            "work_from_date": getdate(doc.attendance_date),
            "work_end_date": getdate(doc.attendance_date),
            "credit": credit,
            "leave_type": "Compensatory Off",
            "status": f"{status}:{diff}",
            "expiry": add_days(
                getdate(doc.attendance_date), grade_doc.custom_comp_off_validity
            ),
            "reason": status,
            "custom_extra_work_hours": worked_hrs_in_delta,
            "custom_reprocess_reference": reprocess_reference,
        }
    )
    comp_off.insert(ignore_permissions=True, ignore_if_duplicate=True)
    try:
        comp_off.submit()
    except Exception:
        if comp_off.docstatus.is_submitted():
            comp_off.cancel()
        frappe.log_error(
            frappe.get_traceback(),
            f"Comp-Off Allocation Failed for {doc.employee} on {doc.attendance_date}",
        )


def is_absence_side_status(status, leave_application=None, attendance_request=None):
    """Absence-side test for one attendance's own fields.

    Callers that already hold the Attendance document should use this instead
    of re-reading it via is_sandwich_absence_side, so that the condition used
    to decide between applying and reverting a sandwich mark stays identical
    to the condition sandwich_attendance/revert_sandwich_attendance apply
    internally.
    """
    if status in ("Absent", "On Leave"):
        return True
    if status == "Half Day" and leave_application and not attendance_request:
        return True
    return False


def is_sandwich_absence_side(employee, date):
    """True only for Absent, On Leave, or a Half Day caused by an approved
    Leave Application. Present/Work From Home/On Duty, a physical Half Day,
    or a Half/Full Day covered by an approved Attendance Request all count
    as "presence" and return False - they block or revert a sandwich mark
    on an adjacent Weekly-Off/Holiday instead of triggering/maintaining one.
    """
    att = frappe.db.get_value(
        "Attendance",
        {"employee": employee, "attendance_date": date, "docstatus": 1},
        ["status", "leave_application", "attendance_request"],
        as_dict=True,
    )
    if not att:
        return False
    return is_absence_side_status(
        att.status, att.leave_application, att.attendance_request
    )


def get_holiday_block(employee, date):
    """Contiguous holiday/weekly-off block containing `date`, as (start, end),
    or None if `date` itself isn't a holiday for the employee. Bounded by
    construction - only ever walks through consecutive holiday days on each
    side, never further back/forward than the block itself."""
    weekly_off_name = get_weekly_off_based_on_date(employee, date)
    if not should_consider_holiday(employee, date, weekly_off_name):
        return None

    block_start = block_end = getdate(date)

    prev_day = add_days(block_start, -1)
    while should_consider_holiday(
        employee, prev_day, get_weekly_off_based_on_date(employee, prev_day)
    ):
        block_start = prev_day
        prev_day = add_days(block_start, -1)

    next_day = add_days(block_end, 1)
    while should_consider_holiday(
        employee, next_day, get_weekly_off_based_on_date(employee, next_day)
    ):
        block_end = next_day
        next_day = add_days(block_end, 1)

    return block_start, block_end


def _mark_date_absent_by_sandwich(employee, _date):
    """Cancel any existing attendance for `_date` and create a fresh Absent
    record tagged as sandwich-marked. Isolated per-date so one bad date
    (e.g. a duplicate/link error) can't abort the rest of the block."""
    try:
        attendance_name = frappe.db.exists(
            "Attendance",
            {"employee": employee, "attendance_date": _date, "docstatus": 1},
        )
        if attendance_name:
            existing = frappe.get_doc("Attendance", attendance_name)
            try:
                existing.cancel()
            except SandwichPolicyError:
                return  # Skip if cannot cancel due to salary processed

        new_attendance = frappe.get_doc(
            {
                "doctype": "Attendance",
                "employee": employee,
                "attendance_date": _date,
                "status": "Absent",
                "custom_attendance_tag": "A",
                "custom_marked_absent_by_sandwich": 1,
            }
        )
        new_attendance.insert(ignore_permissions=True)
        new_attendance.submit()
        new_attendance.add_comment(
            "Comment", frappe._("Marked Absent by Sandwich Policy")
        )
    except Exception as e:
        frappe.log_error(
            f"Failed to sandwich-mark {employee} on {_date}: {e}", "sandwich_attendance"
        )


def sandwich_attendance(doc):
    """Mark a Weekly-Off/Holiday block as Absent by sandwich policy when the
    single day right after it is submitted Absent and the single day right
    before it is also absence-side. Local, same-run check only - no
    historical search."""
    grade = frappe.get_value("Employee", doc.employee, "grade")
    if not grade:
        return

    if not frappe.db.get_value("Employee Grade", grade, "custom_sandwich_flag"):
        return

    if not is_sandwich_absence_side(doc.employee, doc.attendance_date):
        return

    block = get_holiday_block(doc.employee, add_days(doc.attendance_date, -1))
    if not block:
        return
    block_start, block_end = block

    if not is_sandwich_absence_side(doc.employee, add_days(block_start, -1)):
        return

    _date = block_start
    while _date <= block_end:
        _mark_date_absent_by_sandwich(doc.employee, _date)
        _date = add_days(_date, 1)


def _revert_sandwich_block(employee, block_start, block_end):
    sandwich_absents = frappe.get_all(
        "Attendance",
        filters={
            "employee": employee,
            "attendance_date": ("between", (block_start, block_end)),
            "custom_marked_absent_by_sandwich": 1,
            "docstatus": 1,
        },
        fields=["name", "attendance_date"],
        order_by="attendance_date asc",
    )
    for rec in sandwich_absents:
        try:
            att = frappe.get_doc("Attendance", rec.name)
            checkins = frappe.get_all(
                "Employee Checkin",
                filters={"attendance": att.name},
                fields=["*"],
                order_by="time asc",
            )
            att.cancel()
            create_attendance(employee, att.attendance_date, checkins)
        except Exception as e:
            frappe.log_error(
                f"Failed to revert {rec.name}: {e}", "revert_sandwich_attendance"
            )


def revert_sandwich_attendance(doc):
    """Revert sandwich-marked absences on the Weekly-Off/Holiday block(s)
    immediately touching this date, once this date is no longer absence-side.
    Local, same-run check only - no historical search."""
    grade = frappe.db.get_value("Employee", doc.employee, "grade")
    if not grade:
        return

    if not frappe.db.get_value("Employee Grade", grade, "custom_sandwich_flag"):
        return

    if is_sandwich_absence_side(doc.employee, doc.attendance_date):
        return  # still absence-side (e.g. leave-driven Half Day) - nothing to revert

    current_date = getdate(doc.attendance_date)
    for neighbor in (add_days(current_date, -1), add_days(current_date, 1)):
        block = get_holiday_block(doc.employee, neighbor)
        if not block:
            continue
        _revert_sandwich_block(doc.employee, block[0], block[1])


def should_consider_holiday(employee: str, date, weekly_holiday_name=None):
    from frappe.query_builder import DocType
    from frappe.query_builder import functions as fn

    if not is_holiday_for_employee(employee, date, weekly_holiday_name):
        return False

    date = getdate(date)

    Employee_Checkin = DocType("Employee Checkin")
    query = (
        frappe.qb.from_(Employee_Checkin)
        .select(Employee_Checkin.name)
        .where(fn.Date(Employee_Checkin.shift_start) == date)
        .where(Employee_Checkin.employee == employee)
    )
    checkin_exists = query.run(as_dict=True)

    attendance_request_exists = frappe.db.exists(
        "Attendance Request",
        {
            "employee": employee,
            "from_date": ("<=", date),
            "to_date": (">=", date),
            "docstatus": 1,
        },
    )

    leave_applications = frappe.db.exists(
        "Leave Application",
        {
            "employee": employee,
            "from_date": ("<=", date),
            "to_date": (">=", date),
            "docstatus": 1,
        },
    )
    if checkin_exists or attendance_request_exists or leave_applications:
        return False

    return True


class SandwichPolicyError(frappe.ValidationError):
    pass
