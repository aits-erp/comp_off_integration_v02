from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, get_datetime, get_first_day, get_last_day, getdate

from real_group_hrms.helper.attendance_helper import create_attendance
from real_group_hrms.utils import (
    convert_time_to_hours,
    get_holiday_dates_for_employee,
    get_weekly_off_based_on_date,
    half_types_differ,
    is_holiday_for_employee,
)


def validate(doc, method=None):
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
                "Cannot cancel: Salary for this period has already been submitted."
            ),
            SandwichPolicyError,
        )


def on_cancel(doc, method=None):
    cancel_incentive_or_c_off(doc)


def before_delete(doc, method=None):
    if is_salary_processed(doc):
        frappe.throw(
            frappe._(
                "Cannot delete: Salary for this period has already been submitted."
            )
        )


def on_submit(doc, method=None):
    update_attendance_status(doc)
    update_attendance_tag(doc)
    if frappe.flags.in_reprocess_attendance:
        return
    if doc.custom_marked_absent_by_sandwich:
        return
    frappe.enqueue(allocate_incentive, doc=doc, queue="long", enqueue_after_commit=True)
    frappe.enqueue(allocate_c_off, doc=doc, queue="long", enqueue_after_commit=True)

    if doc.status == "Absent":
        frappe.enqueue(
            sandwich_attendance, doc=doc, queue="long", enqueue_after_commit=True
        )
    else:
        frappe.enqueue(
            revert_sandwich_attendance, doc=doc, queue="long", enqueue_after_commit=True
        )


def is_salary_processed(doc):
    return frappe.db.exists(
        "Salary Slip",
        {
            "employee": doc.employee,
            "start_date": ["<=", doc.attendance_date],
            "end_date": [">=", doc.attendance_date],
            "docstatus": 1,
        },
    )


def cancel_incentive_or_c_off(doc):
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
        c_off_doc.cancel()

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
    if doc.leave_application and doc.status == "Half Day":
        is_holiday = is_holiday_for_employee(doc.employee, doc.attendance_date)
        is_lwp = frappe.get_value("Leave Type", doc.leave_type, "is_lwp")
        if is_holiday and is_holiday.get("is_half_day"):
            leave_half_type = frappe.get_value("Leave Application", doc.leave_application, "custom_half_type")
            if half_types_differ(is_holiday.get("half_type"), leave_half_type) or not leave_half_type:
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
            request_half_type = frappe.get_value("Attendance Request", doc.attendance_request, "custom_half_type")
            leave_half_type = frappe.get_value("Leave Application", doc.leave_application, "custom_half_type")
            if (
                request_half_day_date
                and leave_half_date
                and getdate(request_half_day_date) == getdate(leave_half_date)
                and (half_types_differ(request_half_type, leave_half_type) or not request_half_type or not leave_half_type)
            ):
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
        leave_half_type = frappe.get_cached_value("Leave Application", doc.leave_application, "custom_half_type")
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
            and half_types_differ(holiday_half_type, getattr(request, "custom_half_type", None))
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
    log_types = frappe.get_all("Employee Checkin", filters=fallback_filters, pluck="log_type")
    if log_types:
        return [log_type for log_type in log_types if log_type]

    fallback_filters = [
        ["employee", "=", employee],
        ["time", ">=", start],
        ["time", "<", end],
    ]
    log_types = frappe.get_all("Employee Checkin", filters=fallback_filters, pluck="log_type")
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


def allocate_incentive(doc):
    def _create_additional_salary(employee: str, amount, incentive_log_name):
        new_additional_salary = frappe.get_doc(
            dict(
                doctype="Additional Salary",
                employee=employee,
                payroll_date=get_last_day(doc.attendance_date),
                salary_component="Incentives",
                amount=amount,
                custom_incentive_reference=incentive_log_name,
                custom_reprocess_reference=doc.custom_reprocess_reference,
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
    if holiday and holiday.get("is_holiday") and not (checkins or has_attendance_checkins(doc)):
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
    month_start = get_first_day(doc.attendance_date)
    month_end = get_last_day(doc.attendance_date)
    additional_incentive = (earning / (date_diff(month_end, month_start) + 1)) * credit

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
    if holiday and holiday.get("is_holiday") and not (checkins or has_attendance_checkins(doc)):
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


def sandwich_attendance(doc):
    """Mark holidays/weekly-offs as Absent by sandwich policy when an absence is submitted."""
    grade = frappe.get_value("Employee", doc.employee, "grade")
    if not grade:
        return

    is_sandwich = frappe.db.get_value("Employee Grade", grade, "custom_sandwich_flag")
    if not is_sandwich or doc.status != "Absent":
        return

    to_mark_absent = get_mark_to_absent(doc.employee, doc.attendance_date)
    if not to_mark_absent:
        return

    for _date in to_mark_absent:
        attendance_name = frappe.db.exists(
            "Attendance",
            {"employee": doc.employee, "attendance_date": _date, "docstatus": 1},
        )

        if attendance_name:
            existing = frappe.get_doc("Attendance", attendance_name)
            # Only override if not already marked by sandwich
            try:
                existing.cancel()
            except SandwichPolicyError:
                continue  # Skip if cannot cancel due to salary processed
        # Create fresh Absent
        new_attendance = frappe.get_doc(
            {
                "doctype": "Attendance",
                "employee": doc.employee,
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


def revert_sandwich_attendance(doc):
    """Revert sandwich-marked absences if sandwich condition breaks (including for back-dated changes)."""
    grade = frappe.db.get_value("Employee", doc.employee, "grade")
    if not grade:
        return

    is_sandwich = frappe.db.get_value("Employee Grade", grade, "custom_sandwich_flag")
    if not is_sandwich:
        return

    # Only proceed if current status is not Absent
    if doc.status == "Absent":
        return

    current_date = getdate(doc.attendance_date)

    # Find previous Present/WFH/On Duty (left boundary)
    prev_present = frappe.db.get_value(
        "Attendance",
        {
            "employee": doc.employee,
            "attendance_date": ("<", current_date),
            "status": ["in", ["Present", "Work From Home", "On Duty"]],
            "docstatus": 1,
        },
        "attendance_date",
        order_by="attendance_date desc",
    )

    # Find next Present/WFH/On Duty (right boundary)
    next_present = frappe.db.get_value(
        "Attendance",
        {
            "employee": doc.employee,
            "attendance_date": (">", current_date),
            "status": ["in", ["Present", "Work From Home", "On Duty"]],
            "docstatus": 1,
        },
        "attendance_date",
        order_by="attendance_date asc",
    )

    if not prev_present and not next_present:
        return

    from_date = getdate(prev_present) if prev_present else current_date
    to_date = getdate(next_present) if next_present else current_date
    to_mark_absent = get_mark_to_absent(doc.employee, doc.attendance_date)

    sandwich_absents = frappe.get_all(
        "Attendance",
        filters={
            "employee": doc.employee,
            "attendance_date": ("between", (from_date, to_date)),
            "custom_marked_absent_by_sandwich": 1,
            "docstatus": 1,
        },
        fields=["name", "attendance_date"],
        order_by="attendance_date asc",
    )

    for rec in sandwich_absents:
        if to_mark_absent and getdate(rec.attendance_date) in to_mark_absent:
            continue

        att = frappe.get_doc("Attendance", rec.name)

        before = frappe.db.get_value(
            "Attendance",
            {
                "employee": doc.employee,
                "attendance_date": add_days(att.attendance_date, -1),
                "docstatus": 1,
            },
            "status",
        )
        after = frappe.db.get_value(
            "Attendance",
            {
                "employee": doc.employee,
                "attendance_date": add_days(att.attendance_date, 1),
                "docstatus": 1,
            },
            "status",
        )
        if is_sandwich_boundary_status(before) and is_sandwich_boundary_status(after):
            continue

        try:
            checkins = frappe.get_all(
                "Employee Checkin",
                filters={"attendance": att.name},
                fields=["*"],
                order_by="time asc",
            )
            att.cancel()
            create_attendance(doc.employee, att.attendance_date, checkins)
        except Exception as e:
            frappe.log_error(
                f"Failed to revert {att.name}: {e}", "revert_sandwich_attendance"
            )


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


def get_mark_to_absent(employee, for_date):
    weekly_off_name = get_weekly_off_based_on_date(employee, for_date)
    safe_limit = add_days(for_date, -30)
    holidays = get_holiday_dates_for_employee(employee, safe_limit, for_date)
    filters = [
        ["employee", "=", employee],
        ["attendance_date", "<", for_date],
        ["attendance_date", "not in", holidays],
        ["status", "in", ["Present", "Work From Home", "On Duty"]],
        ["docstatus", "=", 1],
    ]
    nearest_present = frappe.db.get_value(
        "Attendance",
        filters,
        "attendance_date",
        order_by="attendance_date desc",
    )
    if not nearest_present:
        return False

    records = frappe.get_all(
        "Attendance",
        filters={
            "employee": employee,
            "attendance_date": [">=", nearest_present],
            "docstatus": 1,
        },
        fields=["name", "attendance_date", "status"],
        order_by="attendance_date asc",
    )
    if not records:
        return False
    records_by_date = {getdate(r.attendance_date): frappe._dict(r) for r in records}
    to_mark_absent = set()
    current = getdate(nearest_present)
    to_date = getdate(for_date)
    while current <= to_date:
        if not should_consider_holiday(employee, current, weekly_off_name):
            current = add_days(current, 1)
            continue

        # Detect holiday block
        # For example if two consecutive holiday/weekly off then find next non holiday date

        block_start = current
        block_end = current
        next_day = add_days(block_end, 1)
        weekly_off_for_next_day = get_weekly_off_based_on_date(employee, next_day)
        while should_consider_holiday(employee, next_day, weekly_off_for_next_day):
            block_end = next_day
            next_day = add_days(block_end, 1)
            weekly_off_for_next_day = get_weekly_off_based_on_date(employee, next_day)

        prev_date = add_days(block_start, -1)
        next_date = add_days(block_end, 1)

        pre_attendance = records_by_date.get(prev_date)
        post_attendance = records_by_date.get(next_date)

        if not pre_attendance:
            pre_attendance = frappe.db.get_value(
                "Attendance",
                {"employee": employee, "attendance_date": prev_date, "docstatus": 1},
                ["name", "attendance_date", "status"],
                as_dict=True,
            )

        if not post_attendance:
            post_attendance = frappe.db.get_value(
                "Attendance",
                {"employee": employee, "attendance_date": next_date, "docstatus": 1},
                ["name", "attendance_date", "status"],
                as_dict=True,
            )
        # 1. back and post both exists
        # 2. only back exists
        # 3. only post exists
        # 4. both does not exists

        if pre_attendance and post_attendance:
            pre_attendance = frappe._dict(pre_attendance)
            post_attendance = frappe._dict(post_attendance)
            if is_sandwich_boundary_status(
                pre_attendance.status
            ) and is_sandwich_boundary_status(post_attendance.status):
                d = block_start
                while d <= block_end:
                    to_mark_absent.add(d)
                    d = add_days(d, 1)

        elif pre_attendance and not post_attendance and next_date <= getdate(for_date):
            pre_attendance = frappe._dict(pre_attendance)
            if is_sandwich_boundary_status(pre_attendance.status):
                d = block_start
                while d <= block_end:
                    to_mark_absent.add(d)
                    d = add_days(d, 1)
        elif not pre_attendance and post_attendance:
            post_attendance = frappe._dict(post_attendance)
            if is_sandwich_boundary_status(post_attendance.status):
                d = block_start
                while d <= block_end:
                    to_mark_absent.add(d)
                    d = add_days(d, 1)
        elif not pre_attendance and not post_attendance:
            d = block_start
            while d <= block_end:
                to_mark_absent.add(d)
                d = add_days(d, 1)
        current = add_days(block_end, 1)

    return list(to_mark_absent)


def is_sandwich_boundary_status(status):
    return status in {"Absent", "On Leave"}


class SandwichPolicyError(frappe.ValidationError):
    pass
