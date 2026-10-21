from collections import defaultdict
from datetime import datetime, timedelta

import frappe
from frappe.utils import (
    cstr,
    format_time,
    get_datetime,
    get_link_to_form,
    get_time,
    get_timedelta,
    getdate,
)

from real_group_hrms.utils import convert_time_to_minutes


def get_bio_log_filter_values(employee_doc):
    if not employee_doc:
        return {}

    return {
        "company": employee_doc.company,
        "branch": employee_doc.branch,
        "division": employee_doc.custom_division,
        "department": employee_doc.department,
    }


def ensure_punch_datetime(log):
    if getattr(log, "punch_datetime", None):
        punch_dt = get_datetime(log.punch_datetime)
    elif getattr(log, "punch_date", None) and getattr(log, "punch_time", None):
        punch_dt = datetime.combine(getdate(log.punch_date), get_time(log.punch_time))
    else:
        punch_dt = None

    if punch_dt:
        log.punch_datetime = punch_dt

    return punch_dt


def mark_bio_log(log_name: str, status: str, message: str, filter_values=None):
    values = {
        "is_processed": status,
        "message": message,
    }

    if filter_values:
        values.update(filter_values)

    try:
        frappe.db.set_value(
            "bioattendancelog",
            log_name,
            values,
            update_modified=False,
        )
    except Exception:
        frappe.db.set_value(
            "bioattendancelog",
            log_name,
            {
                "is_processed": status,
                "message": message,
            },
            update_modified=False,
        )
    frappe.db.commit()


def is_cross_day_shift_type(shift_type: dict | frappe._dict | None) -> bool:
    if not shift_type:
        return False

    if shift_type.get("custom_is_cross_day"):
        return True

    start_time = shift_type.get("start_time")
    end_time = shift_type.get("end_time")
    if not (start_time and end_time):
        return False

    return get_time(start_time) > get_time(end_time)


def process():
    logs = frappe.get_all(
        "bioattendancelog",
        filters={"is_processed": "N"},
        fields=["*", "employee_id as employee"],
        limit_page_length=10000,
        order_by="punch_date asc, punch_time asc",
    )

    for log in logs:
        ensure_punch_datetime(log)

    logs.sort(key=lambda log: log.get("punch_datetime") or datetime.min)

    in_logs = [log for log in logs if log.punch_direction == "I"]
    out_logs = [log for log in logs if log.punch_direction == "O"]
    try:
        process_employee_checkin(in_logs)
        process_employee_checkout(out_logs)
    except Exception as e:
        raise e


def process_employee_checkin(logs):
    log_map = defaultdict(list)

    for log in logs:
        log_map[log["employee"]].append(log)
    checkins = dict(log_map)

    for emp, emp_logs in checkins.items():
        if not frappe.db.exists("Employee", emp):
            for log in emp_logs:
                mark_bio_log(
                    log.name,
                    "E",
                    f"Employee {get_link_to_form('Employee', emp)} does not exist",
                )
            continue
        employee = frappe.get_doc("Employee", emp, for_update=False)
        grade = employee.grade
        filter_values = get_bio_log_filter_values(employee)

        for log in emp_logs:
            try:
                punch_dt = ensure_punch_datetime(log)
                if not punch_dt:
                    mark_bio_log(
                        log.name,
                        "E",
                        f"Missing punch date/time for employee {get_link_to_form('Employee', emp)}",
                        filter_values=filter_values,
                    )
                    continue

                first_checkin_shift = get_first_checkin_for_the_day(
                    emp, for_date=punch_dt, punch_direction=log.punch_direction
                )
                # If we have a existing checkin, we don't need to calculate which shift to assign
                # Just use shift from last checkin
                if first_checkin_shift:
                    shift_info = fetch_shift_details(
                        first_checkin_shift, punch_dt, grade
                    )

                    doc = frappe.get_doc(
                        {
                            "doctype": "Employee Checkin",
                            "employee": emp,
                            "time": punch_dt,
                            "shift": first_checkin_shift,
                            "log_type": "IN",
                            "custom_bio_log_id": log.name,
                            "device_id": log.terminal_id,
                            "shift_start": shift_info.start_datetime,
                            "shift_end": shift_info.end_datetime,
                            "shift_actual_start": shift_info.actual_start,
                            "shift_actual_end": shift_info.actual_end,
                        }
                    )
                    doc.flags.is_shift_fetch_required = False
                    doc.insert()

                else:
                    for_date = getdate(log.punch_date)
                    allowed_shifts = get_employee_allowed_shifts(emp, for_date)
                    closest_shift = find_closest_shift_from_punch_time(
                        allowed_shifts,
                        punch_dt,
                        date=for_date,
                        log_type="IN",
                        direction_hint=log.punch_direction,
                    )

                    shift_info = fetch_shift_details(closest_shift, punch_dt, grade)
                    doc = frappe.get_doc(
                        {
                            "doctype": "Employee Checkin",
                            "employee": emp,
                            "time": punch_dt,
                            "shift": closest_shift,
                            "log_type": "IN",
                            "custom_bio_log_id": log.name,
                            "device_id": log.terminal_id,
                            "shift_start": shift_info.start_datetime,
                            "shift_end": shift_info.end_datetime,
                            "shift_actual_start": shift_info.actual_start,
                            "shift_actual_end": shift_info.actual_end,
                        }
                    )
                    doc.flags.is_shift_fetch_required = False
                    doc.insert()

                mark_bio_log(
                    log.name,
                    "Y",
                    f"Checkin created {get_link_to_form('Employee Checkin', doc.name)}",
                    filter_values=filter_values,
                )
            except Exception as e:
                message = cstr(e)
                if "Duplicate entry" in message and "custom_bio_log_id" in message:
                    existing_checkin = frappe.db.get_value(
                        "Employee Checkin",
                        {"custom_bio_log_id": log.name},
                        "name",
                    )
                    if existing_checkin:
                        mark_bio_log(
                            log.name,
                            "E",
                            f"Error processing checkout for employee {get_link_to_form('Employee', emp)}: Bio log already linked to {get_link_to_form('Employee Checkin', existing_checkin)}",
                            filter_values=filter_values,
                        )
                        continue
                mark_bio_log(
                    log.name,
                    "E",
                    f"Error processing checkin for employee {get_link_to_form('Employee', emp)}: {e!s}",
                    filter_values=filter_values,
                )
                continue


def get_valid_owning_shift_for_checkout(employee: str, punch_dt: datetime, grade: str):
    def _get_shift_data_from_candidate(candidate):
        shift_name = candidate.get("shift")
        if not shift_name:
            return None

        shift_start = candidate.get("shift_start")
        shift_end = candidate.get("shift_end")
        shift_actual_start = candidate.get("shift_actual_start")
        shift_actual_end = candidate.get("shift_actual_end")
        candidate_time = candidate.get("time")
        candidate_dt = get_datetime(candidate_time) if candidate_time else punch_dt

        if not (shift_start and shift_end and shift_actual_start and shift_actual_end):
            shift_info = fetch_shift_details(shift_name, candidate_dt, grade)
            shift_start = shift_info.start_datetime
            shift_end = shift_info.end_datetime
            shift_actual_start = shift_info.actual_start
            shift_actual_end = shift_info.actual_end

        if not (shift_actual_start and shift_actual_end):
            return None

        return frappe._dict(
            {
                "shift": shift_name,
                "shift_start": shift_start,
                "shift_end": shift_end,
                "shift_actual_start": get_datetime(shift_actual_start),
                "shift_actual_end": get_datetime(shift_actual_end),
            }
        )

    # Strict shift lock for OUT:
    # always pick latest unmatched IN (same-day, cross-day, overtime included).
    latest_checkout_time = frappe.db.get_value(
        "Employee Checkin",
        filters={
            "employee": employee,
            "log_type": "OUT",
            "time": ["<=", punch_dt],
        },
        fieldname="time",
        order_by="time desc",
    )
    latest_checkout_time = (
        get_datetime(latest_checkout_time) if latest_checkout_time else None
    )

    in_filters = [
        ["employee", "=", employee],
        ["log_type", "=", "IN"],
        ["time", "<=", punch_dt],
    ]
    if latest_checkout_time:
        in_filters.append(["time", ">", latest_checkout_time])

    candidate_checkins = frappe.get_all(
        "Employee Checkin",
        filters=in_filters,
        fields=[
            "name",
            "shift",
            "shift_start",
            "shift_end",
            "shift_actual_start",
            "shift_actual_end",
            "time",
        ],
        order_by="time desc",
        limit_page_length=1,
    )
    if not candidate_checkins:
        return None

    return _get_shift_data_from_candidate(candidate_checkins[0])


def process_employee_checkout(logs):
    log_map = defaultdict(list)

    for log in logs:
        log_map[log["employee"]].append(log)
    checkouts = dict(log_map)

    for emp, emp_logs in checkouts.items():
        if not frappe.db.exists("Employee", emp):
            for log in emp_logs:
                mark_bio_log(
                    log.name,
                    "E",
                    f"Employee {get_link_to_form('Employee', emp)} does not exist",
                )
            continue
        employee = frappe.get_doc("Employee", emp, for_update=False)
        grade = employee.grade
        filter_values = get_bio_log_filter_values(employee)

        for log in emp_logs:
            try:
                punch_dt = ensure_punch_datetime(log)
                if not punch_dt:
                    mark_bio_log(
                        log.name,
                        "E",
                        f"Missing punch date/time for employee {get_link_to_form('Employee', emp)}",
                        filter_values=filter_values,
                    )
                    continue

                owning_shift_data = get_valid_owning_shift_for_checkout(
                    emp, punch_dt, grade
                )

                use_owning_shift = bool(
                    owning_shift_data and owning_shift_data.get("shift")
                )

                if use_owning_shift:
                    shift_name = owning_shift_data.get("shift")
                    shift_start = owning_shift_data.get("shift_start")
                    shift_end = owning_shift_data.get("shift_end")
                    shift_actual_start = owning_shift_data.get("shift_actual_start")
                    shift_actual_end = owning_shift_data.get("shift_actual_end")
                    doc = frappe.get_doc(
                        {
                            "doctype": "Employee Checkin",
                            "employee": emp,
                            "time": punch_dt,
                            "shift": shift_name,
                            "log_type": "OUT",
                            "custom_bio_log_id": log.name,
                            "device_id": log.terminal_id,
                            "shift_start": shift_start,
                            "shift_end": shift_end,
                            "shift_actual_start": shift_actual_start,
                            "shift_actual_end": shift_actual_end,
                        }
                    )
                    doc.flags.is_shift_fetch_required = False
                    doc.insert()
                    frappe.db.commit()

                if not use_owning_shift:
                    for_date = getdate(log.punch_date)
                    allowed_shifts = get_employee_allowed_shifts(emp, for_date)
                    closest_shift = find_closest_shift_from_punch_time(
                        allowed_shifts,
                        punch_dt,
                        date=for_date,
                        log_type="OUT",
                        direction_hint=log.punch_direction,
                    )

                    shift_type = get_shift_type(closest_shift)
                    is_cross_day = is_cross_day_shift_type(shift_type)
                    shift_info = fetch_shift_details(
                        closest_shift, punch_dt, grade, is_checkout=is_cross_day
                    )
                    doc = frappe.get_doc(
                        {
                            "doctype": "Employee Checkin",
                            "employee": emp,
                            "time": punch_dt,
                            "shift": closest_shift,
                            "log_type": "OUT",
                            "custom_bio_log_id": log.name,
                            "device_id": log.terminal_id,
                            "shift_start": shift_info.start_datetime,
                            "shift_end": shift_info.end_datetime,
                            "shift_actual_start": shift_info.actual_start,
                            "shift_actual_end": shift_info.actual_end,
                        }
                    )
                    doc.flags.is_shift_fetch_required = False
                    doc.insert()
                    frappe.db.commit()
                mark_bio_log(
                    log.name,
                    "Y",
                    f"Checkout created {get_link_to_form('Employee Checkin', doc.name)}",
                    filter_values=filter_values,
                )
            except Exception as e:
                message = cstr(e)
                if "Duplicate entry" in message and "custom_bio_log_id" in message:
                    existing_checkin = frappe.db.get_value(
                        "Employee Checkin",
                        {"custom_bio_log_id": log.name},
                        "name",
                    )
                    if existing_checkin:
                        mark_bio_log(
                            log.name,
                            "E",
                            f"Error processing checkout for employee {get_link_to_form('Employee', emp)}: Bio log already linked to {get_link_to_form('Employee Checkin', existing_checkin)}",
                            filter_values=filter_values,
                        )
                        continue
                mark_bio_log(
                    log.name,
                    "E",
                    f"Error processing checkout for employee {get_link_to_form('Employee', emp)}: {e!s}",
                    filter_values=filter_values,
                )
                continue


def find_closest_shift_from_punch_time(
    allowed_shifts: list[str],
    punch_time: str | timedelta | datetime,
    date=None,
    log_type: str = "IN",
    direction_hint: str | None = None,
):
    if not allowed_shifts:
        return None

    reference_date = getdate(date) if date else getdate(frappe.utils.now_datetime())

    # Nearest-shift resolver with direction awareness:
    # - IN  -> nearest shift start
    # - OUT -> nearest shift end
    resolved_log_type = (log_type or "").upper()
    direction = (direction_hint or "").upper()
    if direction == "I":
        resolved_log_type = "IN"
    elif direction == "O":
        resolved_log_type = "OUT"
    if resolved_log_type not in {"IN", "OUT"}:
        resolved_log_type = "IN"

    punch_dt = (
        get_datetime(punch_time)
        if isinstance(punch_time, datetime)
        else datetime.combine(reference_date, get_time(punch_time))
    )

    shifts = frappe.db.get_all(
        "Shift Type",
        filters={"name": ["in", allowed_shifts]},
        fields=[
            "name",
            "start_time",
            "end_time",
            "custom_is_cross_day",
            "custom_early_entry_grace_period",
            "custom_late_exit_grace_period",
        ],
    )

    shift_candidates = []
    is_checkout_context = resolved_log_type == "OUT"
    for shift in shifts:
        if not shift.get("start_time") or not shift.get("end_time"):
            continue

        is_cross_day = is_cross_day_shift_type(shift)
        start_datetime, end_datetime = get_shift_timings(
            frappe._dict(shift),
            punch_dt,
            grade=None,
            # OUT fallback should resolve cross-day shifts on T-1 window.
            is_checkout=(is_checkout_context and is_cross_day),
        )
        anchor_datetime = end_datetime if is_checkout_context else start_datetime

        shift_candidates.append(
            {
                "name": shift.get("name"),
                "start_datetime": start_datetime,
                "anchor_datetime": anchor_datetime,
            }
        )
    if not shift_candidates:
        return None

    closest_shift = min(
        shift_candidates,
        key=lambda s: (
            abs((punch_dt - s["anchor_datetime"]).total_seconds()),
            s["start_datetime"],
        ),
    )

    return closest_shift["name"]


def should_recalculate_shift_for_boundary_switch(
    employee: str, punch_dt: datetime, existing_shift_data: dict
) -> bool:
    """
    Guard for cross-day shift switches.

    If an employee already punched OUT in the current cross-day window and the new IN
    is very close to another allowed shift start, prefer recalculating shift instead of
    reusing the previous day's shift.
    """
    shift_name = existing_shift_data.get("shift")
    shift_start = existing_shift_data.get("shift_start")
    shift_end = existing_shift_data.get("shift_end")
    last_in_time = existing_shift_data.get("time")

    if not (shift_name and shift_start and shift_end and last_in_time):
        return False

    shift_start = get_datetime(shift_start)
    shift_end = get_datetime(shift_end)

    # Apply only to cross-day windows.
    if getdate(shift_start) == getdate(shift_end):
        return False

    # Boundary condition: punch on the second day of that cross-day shift.
    if getdate(punch_dt) != getdate(shift_end):
        return False

    # Prefer existing checkout if already created.
    existing_out = frappe.db.get_value(
        "Employee Checkin",
        filters={
            "employee": employee,
            "log_type": "OUT",
            "time": ["between", [last_in_time, punch_dt]],
        },
        fieldname="time",
        order_by="time desc",
    )
    if not existing_out:
        # In this flow IN logs are processed before OUT logs, so checkout might not yet exist.
        # Use raw bio OUT punches as supporting evidence for shift switch.
        from_dt = get_datetime(last_in_time)
        to_dt = get_datetime(punch_dt)
        start_date = getdate(from_dt)
        end_date = getdate(to_dt)

        out_logs = frappe.db.sql(
            """
            SELECT
                name, punch_date, punch_time, punch_date_backup
            FROM
                `tabbioattendancelog`
            WHERE
                employee_id = %s
                AND punch_direction = 'O'
                AND punch_date >= %s
                AND punch_date <= %s
            ORDER BY
                punch_date ASC, punch_time ASC
            """,
            (employee, str(start_date), str(end_date)),
            as_dict=True,
        )

        has_out_punch_between = False
        for out_log in out_logs:
            out_dt = None
            if out_log.get("punch_date_backup"):
                out_dt = get_datetime(out_log.get("punch_date_backup"))
            elif out_log.get("punch_date") and out_log.get("punch_time"):
                out_dt = datetime.combine(
                    getdate(out_log.get("punch_date")),
                    get_time(out_log.get("punch_time")),
                )

            if out_dt and from_dt <= out_dt <= to_dt:
                has_out_punch_between = True
                break

        if not has_out_punch_between:
            return False

    # Recalculate only when another allowed shift starts near this punch.
    for_date = getdate(punch_dt)
    allowed_shifts = get_employee_allowed_shifts(employee, for_date)
    for allowed_shift in allowed_shifts:
        if allowed_shift == shift_name:
            continue

        candidate_shift = get_shift_type(allowed_shift)
        if not candidate_shift or not candidate_shift.start_time:
            continue

        candidate_start = (
            datetime.combine(for_date, datetime.min.time()) + candidate_shift.start_time
        )
        delta_minutes = abs((punch_dt - candidate_start).total_seconds()) / 60
        if delta_minutes <= 180:
            return True

    return False


def get_first_checkin_for_the_day(
    employee: str, for_date, for_checkout=False, punch_direction: str | None = None
):
    """
    Stable shift resolver.

    Rules:
    - Shift is resolved ONLY once per work date (first IN)
    - Subsequent INs reuse the same shift
    - OUT always reuses the owning IN's shift
    - Cross-day handled by shift definition
    """

    punch_dt = get_datetime(for_date)
    punch_date = getdate(punch_dt)

    # ----------------------------------
    # CHECKOUT → reuse latest IN shift
    # ----------------------------------
    if for_checkout:
        previous_day_start = datetime.combine(
            punch_date - timedelta(days=1), datetime.min.time()
        )
        return frappe.db.get_value(
            "Employee Checkin",
            filters={
                "employee": employee,
                "log_type": "IN",
                "time": ["between", [previous_day_start, punch_dt]],
            },
            fieldname=[
                "shift",
                "shift_start",
                "shift_end",
                "shift_actual_start",
                "shift_actual_end",
            ],
            order_by="time desc",
            as_dict=True,
        )

    # ----------------------------------
    # CHECKIN → reuse last shift if punch is within its window
    # ----------------------------------
    existing_shift_data = frappe.db.get_value(
        "Employee Checkin",
        filters={
            "employee": employee,
            "log_type": "IN",  # 🔑 CRITICAL
            "time": ["<=", punch_dt],
        },
        fieldname=["shift", "shift_start", "shift_end", "time"],
        order_by="time desc",
        as_dict=True,
    )

    if existing_shift_data:
        shift_end = existing_shift_data.get("shift_end")

        # ❌ Do NOT reuse if shift already ended
        if shift_end and punch_dt > get_datetime(shift_end):
            existing_shift_data = None

    if existing_shift_data:
        if should_recalculate_shift_for_boundary_switch(
            employee=employee,
            punch_dt=punch_dt,
            existing_shift_data=existing_shift_data,
        ):
            existing_shift_data = None

    if existing_shift_data:
        existing_shift = existing_shift_data.get("shift")
        shift_end = existing_shift_data.get("shift_end")
        if existing_shift and shift_end and punch_dt < get_datetime(shift_end):
            return existing_shift

    # ----------------------------------
    # FIRST IN OF THE DAY → resolve shift
    # ----------------------------------
    allowed_shifts = get_employee_allowed_shifts(employee, punch_date)
    if not allowed_shifts:
        return None

    shift_name = find_closest_shift_from_punch_time(
        allowed_shifts=allowed_shifts,
        punch_time=punch_dt,
        date=punch_date,
        log_type="IN",
        direction_hint=punch_direction,
    )

    if not shift_name:
        return None

    shift = frappe.get_doc("Shift Type", shift_name)

    punch_delta = get_timedelta(format_time(get_time(punch_dt)))

    # Cross-day early morning → belongs to same shift
    if shift.custom_is_cross_day and punch_delta <= shift.end_time:
        return shift.name

    return shift.name


def fetch_shift_details(
    shift_type: str, for_timestamp: datetime, grade: str, is_checkout=False
) -> dict:
    shift_type = get_shift_type(shift_type)
    if isinstance(for_timestamp, str):
        for_timestamp = get_datetime(for_timestamp)

    start_grace = timedelta(
        minutes=convert_time_to_minutes(shift_type.custom_early_entry_grace_period)
    )

    if not shift_type:
        return frappe._dict()

    start_datetime, end_datetime = get_shift_timings(
        shift_type, for_timestamp, grade, is_checkout
    )

    actual_start = start_datetime - start_grace
    actual_end = end_datetime + timedelta(
        minutes=convert_time_to_minutes(shift_type.custom_late_exit_grace_period)
    )

    return frappe._dict(
        {
            "shift_type": shift_type,
            "start_datetime": start_datetime,
            "end_datetime": end_datetime,
            "actual_start": actual_start,
            "actual_end": actual_end,
        }
    )


def get_shift_timings(
    shift_type: dict, for_timestamp: datetime, grade, is_checkout: False
) -> tuple:
    """
    The method is similar to hrms.hr.doctype.shift_type.shift_type.get_shift_timings but with
    additional logic to handle grace periods defined at Employee Grade level.
    """
    start_time = shift_type.start_time
    end_time = shift_type.end_time

    # Compute margins
    shift_actual_start = get_time(
        datetime.combine(for_timestamp, datetime.min.time())
        + start_time
        - (
            timedelta(
                minutes=convert_time_to_minutes(
                    shift_type.custom_early_entry_grace_period
                )
            )
        )
    )
    shift_actual_end = get_time(
        datetime.combine(for_timestamp, datetime.min.time())
        + end_time
        + timedelta(
            minutes=convert_time_to_minutes(shift_type.custom_late_exit_grace_period)
        )
    )

    for_time = get_time(for_timestamp.time())
    start_datetime = end_datetime = None

    # --- Case 1: Cross-day shift (e.g. 22:00 → 06:00)
    if start_time > end_time:
        if for_time >= shift_actual_start:
            # Timestamp is within same-day portion (e.g. 22:30)
            start_datetime = (
                datetime.combine(for_timestamp, datetime.min.time()) + start_time
            )
            end_datetime = (
                datetime.combine(for_timestamp + timedelta(days=1), datetime.min.time())
                + end_time
            )
        elif (
            for_time < shift_actual_start
            and for_time > shift_actual_end
            and not is_checkout
        ):
            # if for_timestamp is less than start time, it's within the second day
            start_datetime = (
                datetime.combine(for_timestamp, datetime.min.time()) + start_time
            )
            end_datetime = (
                datetime.combine(for_timestamp + timedelta(days=1), datetime.min.time())
                + end_time
            )
        else:
            # Timestamp after midnight (e.g. 02:00 next day)
            start_datetime = (
                datetime.combine(for_timestamp - timedelta(days=1), datetime.min.time())
                + start_time
            )
            end_datetime = (
                datetime.combine(for_timestamp, datetime.min.time()) + end_time
            )

    # --- Case 2: Same-day shift but punch is after midnight (e.g. shift 11→18, checkout at 01:00)

    elif start_time < end_time and for_time < get_time(start_time) and is_checkout:
        start_datetime = (
            datetime.combine(for_timestamp - timedelta(days=1), datetime.min.time())
            + start_time
        )
        end_datetime = (
            datetime.combine(for_timestamp - timedelta(days=1), datetime.min.time())
            + end_time
        )

    # --- Case 3: Margins that cross midnight (edge cases)
    elif (
        shift_actual_start > shift_actual_end
        and for_time < shift_actual_start
        and get_time(end_time) > shift_actual_end
    ):
        # After-midnight margin → belongs to previous day's shift
        for_timestamp -= timedelta(days=1)
        start_datetime = (
            datetime.combine(for_timestamp, datetime.min.time()) + start_time
        )
        end_datetime = datetime.combine(for_timestamp, datetime.min.time()) + end_time

    elif (
        shift_actual_start > shift_actual_end
        and for_time > shift_actual_end
        and get_time(start_time) < shift_actual_start
    ):
        # Before-midnight margin → belongs to next day's shift
        for_timestamp += timedelta(days=1)
        start_datetime = (
            datetime.combine(for_timestamp, datetime.min.time()) + start_time
        )
        end_datetime = datetime.combine(for_timestamp, datetime.min.time()) + end_time

    # --- Case 4: Regular same-day shift
    else:
        start_datetime = (
            datetime.combine(for_timestamp, datetime.min.time()) + start_time
        )
        end_datetime = datetime.combine(for_timestamp, datetime.min.time()) + end_time

    return start_datetime, end_datetime


def get_shift_type(shift_type_name: str) -> dict:
    return frappe.get_value(
        "Shift Type",
        shift_type_name,
        [
            "name",
            "start_time",
            "end_time",
            "custom_is_cross_day",
            "custom_early_entry_grace_period",
            "custom_late_exit_grace_period",
            "custom_late_entry_grace_period",
            "enable_late_entry_marking",
            "enable_early_exit_marking",
            "custom_early_exit_grace_period",
        ],
        as_dict=1,
    )


@frappe.whitelist()
def get_employee_allowed_shifts(employee: str, for_date=None) -> list[str]:
    employee = frappe.get_doc("Employee", employee)

    shift_from_grade = frappe.db.get_values(
        "Multiple Shifts", {"parent": employee.grade}, "shift", pluck="shift"
    )

    allowed_shifts = [employee.default_shift]
    allowed_shifts.extend(shift_from_grade)

    for_date = getdate(for_date)
    assigned_shifts = frappe.get_all(
        "Shift Assignment",
        filters={
            "employee": employee.name,
            "start_date": ("<=", for_date),
            "end_date": (">=", for_date),
            "status": "Active",
        },
        pluck="shift_type",
    )
    allowed_shifts.extend(assigned_shifts)

    allowed_shifts = [x for x in allowed_shifts if x is not None]
    allowed_shifts = list(set(allowed_shifts))
    return allowed_shifts
