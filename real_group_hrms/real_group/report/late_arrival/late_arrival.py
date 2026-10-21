import frappe
from frappe.utils import cint, flt


def execute(filters=None):
    year = filters.get("year")
    month = filters.get("month")
    employee = filters.get("employee")
    company = filters.get("company")
    branch = filters.get("branch")
    division = filters.get("division")
    department = filters.get("department")

    if not branch:
        frappe.throw("Branch is mandatory to generate Late Arrival report")

    conditions = ""
    emp_condition = ""
    company_condition = ""
    branch_condition = ""
    division_condition = ""
    department_condition = ""

    if employee:
        emp_condition = f" and e.name = '{employee}'"
    if company:
        company_condition = f" and e.company = '{company}'"
    if branch:
        branch_condition = f" and e.branch = '{branch}'"
    if division:
        division_condition = f" and e.custom_division = '{division}'"
    if department:
        department_condition = f" and e.department = '{department}'"

    conditions = f"{emp_condition} {company_condition} {branch_condition} {division_condition} {department_condition}"

    columns = [
        {"fieldname": "emp_id", "fieldtype": "Data", "label": "Emp ID", "width": "250"},
        {
            "fieldname": "emp_name",
            "fieldtype": "Data",
            "label": "Employee Name",
            "width": "250",
        },
        {
            "fieldname": "division",
            "fieldtype": "Link",
            "options": "Division",
            "label": "Division",
            "width": "180",
        },
        {
            "fieldname": "department",
            "fieldtype": "Link",
            "options": "Department",
            "label": "Department",
            "width": "180",
        },
        {
            "fieldname": "late_count",
            "fieldtype": "Int",
            "label": "Late Count",
            "width": "120",
        },
        {
            "fieldname": "deduction_in_days",
            "fieldtype": "Float",
            "label": "Deduction in Days",
            "width": "150",
        },
    ]

    result = []

    month_numbers = {
        "Jan": 1,
        "Feb": 2,
        "Mar": 3,
        "Apr": 4,
        "May": 5,
        "Jun": 6,
        "Jul": 7,
        "Aug": 8,
        "Sep": 9,
        "Oct": 10,
        "Nov": 11,
        "Dec": 12,
    }

    fr_date = ""
    t_date = ""
    first_day_next_month = ""
    first_day_last_month = ""
    if month and year and month in month_numbers:
        month_start = f"{int(year)}-{month_numbers[month]:02d}-01"
        first_day_last_month = str(frappe.utils.add_to_date(month_start, days=-1))
        first_day_next_month = str(frappe.utils.add_to_date(month_start, months=1))
        fr_date = first_day_last_month
        t_date = first_day_next_month

    start_date = frappe.utils.add_to_date(frappe.utils.getdate(fr_date), days=1)
    end_date = frappe.utils.add_to_date(frappe.utils.getdate(t_date), days=-1)
    month_start_date = start_date
    month_end_date = end_date

    while start_date <= end_date:
        # start_date = frappe.utils.getdate(start_date)
        # formatted_date = frappe.utils.formatdate(start_date, 'YYYY-MM-DD')
        columns.append(
            {"fieldname": str(start_date), "fieldtype": "Data", "label": str(start_date)}
        )

        start_date = frappe.utils.add_to_date(start_date, days=1)

    employee_list = frappe.db.sql(
        f"""
		SELECT
			DISTINCT e.name, e.employee_name, e.custom_division AS division, e.department, e.holiday_list,
			e.custom_weekly_holiday_list, COALESCE(eg.custom_allowed_late_count_days, 0) AS allowed_late_count,
			COALESCE(eg.custom_late_entry_deduction_cycle, 0) AS deduction_cycle
		FROM
			`tabEmployee` e
		LEFT JOIN
			`tabEmployee Checkin` ec ON ec.employee = e.name
		LEFT JOIN
			`tabEmployee Grade` eg ON eg.name = e.grade
		WHERE
		1=1
		{conditions}
		AND ec.time BETWEEN '{fr_date}' AND '{t_date}'
		""",
        as_dict=True,
    )

    for emp in employee_list:
        allowed_late_count = cint(emp.get("allowed_late_count") or 0)
        deduction_cycle = flt(emp.get("deduction_cycle") or 0)
        off_dates = get_holiday_dates(emp.get("holiday_list"), month_start_date, month_end_date)
        off_dates.update(get_weekly_off_dates(
            emp.get("custom_weekly_holiday_list"), month_start_date, month_end_date
        ))
        attendance_request_dates = get_late_reversal_attendance_request_dates(
            emp.get("name"), month_start_date, month_end_date
        )

        sql = frappe.db.sql(
            f"""
			SELECT
				e.name AS employee,
				e.employee_name,
				e.holiday_list,
				DATE(ec.time) AS date,
				(CASE WHEN ec.log_type = 'IN' THEN TIME(ec.time) END) AS in_time,
				(CASE WHEN ec.log_type = 'OUT' THEN TIME(ec.time) END) AS out_time,
				
				MIN(CASE WHEN ec.log_type = 'IN' THEN ec.time END) AS in_date_time,
				MAX(CASE WHEN ec.log_type = 'OUT' THEN ec.time END) AS out_date_time,
				
				TIME(st.start_time) AS shift_start_time,
				TIME(st.end_time) AS shift_end_time,
				ec.shift,
				(CASE WHEN ec.log_type = 'IN' THEN ec.device_id END) as in_device,
				(CASE WHEN ec.log_type = 'OUT' THEN ec.device_id END) as out_device,
				(CASE WHEN ec.log_type = 'IN' THEN ec.custom_area END) as in_area,
				(CASE WHEN ec.log_type = 'OUT' THEN ec.custom_area END) as out_area,
				e.grade,
				-- (CASE WHEN sa.start_date BETWEEN '{fr_date}' AND '{t_date}' AND sa.employee = e.name THEN sa.name ELSE e.default_shift END) AS shift,
				CASE WHEN st.custom_end_across_days = 1 THEN st.custom_end_across_days ELSE 0 END as custom_end_across_days,
				CASE WHEN ec.custom_is_temporary_shift = 1 THEN "Yes" ELSE "No" END as custom_is_temporary_shift
			FROM
				`tabEmployee` AS e
			LEFT JOIN
				`tabEmployee Checkin` AS ec ON e.name = ec.employee
			LEFT JOIN
				`tabShift Type` AS st ON st.name = ec.shift
			LEFT JOIN
				`tabShift Assignment` AS sa ON sa.employee = e.name
			LEFT JOIN
				`tabEmployee Grade` AS eg ON eg.name = e.grade
			WHERE
				1=1
				{conditions}
				AND ec.time BETWEEN '{fr_date}' AND '{t_date}'
				-- AND '{fr_date}' <= ec.time
				-- AND ec.time <= '{t_date}'
				AND e.name = '{emp["name"]}'
				-- AND eg.custom_single_punch_applicable = 1
				-- AND eg.custom_no_punch_applicable = 0
			GROUP BY
				e.name, ec.time
			ORDER BY
				ec.time ASC
		""",
            as_dict=True,
        )

        late_entry_dict = {
            "emp_id": emp["name"],
            "emp_name": emp["employee_name"],
            "division": emp.get("division"),
            "department": emp.get("department"),
        }
        full_day = safe_get_time("08:00:00")
        half_day = safe_get_time("04:00:00")
        absent = safe_get_time("00:00:00")
        fifteen_minutes_in = safe_get_time("00:00:00")
        fifteen_minutes_out = safe_get_time("00:00:00")
        consecutive_late_entries = {}

        if sql:
            first_checkin_by_date = {}
            for row in sql:
                if row.get("in_date_time"):
                    row_date = str(frappe.utils.getdate(row["date"]))
                    if (
                        row_date not in first_checkin_by_date
                        or row["in_date_time"] < first_checkin_by_date[row_date]
                    ):
                        first_checkin_by_date[row_date] = row["in_date_time"]

            for index, data in enumerate(sql):
                formatted = frappe.utils.getdate(data["date"])
                format_date = str(formatted)
                # frappe.log_error(title="first_data", message=data)
                try:
                    if (
                        data["in_time"]
                        and data["out_time"] is None
                        and sql[index + 1]["in_time"] is None
                        and sql[index + 1]["out_time"]
                    ):
                        data["out_time"] = sql[index + 1]["out_time"]
                        data["out_area"] = sql[index + 1]["out_area"]
                        data["out_device"] = sql[index + 1]["out_device"]
                        sql[index + 1]["out_time"] = None

                    if (
                        data["custom_end_across_days"] == 1
                        and data["in_time"] is not None
                        and data["out_time"] is None
                    ):

                        data["out_time"] = sql[index + 1]["out_time"]
                        sql[index + 1]["out_time"] = None
                except Exception as e:
                    msg = str(e)

                """ Fetching grade wise Present, Absent, HalfDay, late entry and early chekout Threshold """
                grade_emp = None
                if data["grade"]:
                    grade_emp = frappe.get_doc("Employee Grade", data["grade"])

                if grade_emp:
                    # full_day = frappe.utils.get_time(grade_emp.custom_present_threshold_hrs)
                    # half_day = frappe.utils.get_time(grade_emp.custom_half_day_threshold_hrs)
                    # absent = frappe.utils.get_time(grade_emp.custom_absent_threshold_hrs)
                    if grade_emp.custom_check_in_grace_time is not None:
                        fifteen_minutes_in = safe_get_time(
                            grade_emp.custom_check_in_grace_time
                        )
                    if grade_emp.custom_check_out_grace_time is not None:
                        fifteen_minutes_out = safe_get_time(
                            grade_emp.custom_check_out_grace_time
                        )
                    late_count_threshold = grade_emp.custom_allowed_late_count_days or 0

                """SHIFT START TIME AND END TIME FULL DAY HALF DAY ABSENT THRESHOLD"""

                st = None
                et = None
                half_day_late_threshold_seconds = 0
                if data["shift"]:
                    shift = frappe.get_doc("Shift Type", data["shift"])
                    full_day = safe_get_time(shift.custom_present_threshold, "08:00:00")
                    half_day = safe_get_time(shift.custom_half_day_threshold, "04:00:00")
                    absent = safe_get_time(shift.custom_absent_threshold, "00:00:00")
                    half_day_late_threshold_seconds = (
                        get_duration_seconds(
                            getattr(
                                shift,
                                "custom_working_hours_threshold_for_half_day",
                                None,
                            )
                        )
                        / 2
                    )
                    if shift.custom_late_entry_grace_period is not None:
                        fifteen_minutes_in = safe_get_time(
                            shift.custom_late_entry_grace_period
                        )
                    else:
                        fifteen_minutes_in = safe_get_time("00:00:00")
                    st = shift.start_time
                    et = shift.end_time

                # st = frappe.db.get_value("Shift Type", data["shift"], "start_time")
                # et = frappe.db.get_value("Shift Type", data["shift"], "end_time")
                data["shift_start_time"] = st
                data["shift_end_time"] = et
                shift_type = ""
                if data["shift"]:
                    shift_type = frappe.get_doc("Shift Type", data["shift"])

                """ Handling across days shifts / night shift """

                """ Marking Attendance and Checkin """

                hours = frappe.utils.get_timedelta("00:00:00")
                if data["out_time"] is None and data["in_time"] is None:
                    data["attendance"] = "Missing In and Out"
                elif data["in_time"] is None and data["out_time"]:
                    data["attendance"] = "Missing In"
                elif data["out_time"] is None and data["in_time"]:
                    data["attendance"] = "Missing Out"
                elif data["out_time"] is None:
                    data["attendance"] = "Missing Out"
                elif (
                    data["out_time"] < data["in_time"]
                    and data["custom_end_across_days"] != 1
                ):
                    data["attendance"] = "Invalid Punch"
                elif data["out_time"] > data["in_time"]:
                    hours = data["out_time"] - data["in_time"]
                    data["worked_hours"] = hours
                    if frappe.utils.get_time(hours) >= full_day:
                        data["attendance"] = "Present"
                    elif full_day >= frappe.utils.get_time(hours) >= half_day:
                        data["attendance"] = "Half Day"
                    elif frappe.utils.get_time(hours) < absent:
                        data["attendance"] = "Absent"

                elif (
                    data["out_time"] < data["in_time"]
                    and data["custom_end_across_days"] == 1
                ):
                    twenty_four_hour = frappe.utils.get_timedelta("24:00:00")
                    hours = data["out_time"] + twenty_four_hour - data["in_time"]
                    data["worked_hours"] = hours
                    if frappe.utils.get_time(hours) >= full_day:
                        data["attendance"] = "Present"
                    elif full_day >= frappe.utils.get_time(hours) >= half_day:
                        data["attendance"] = "Half Day"
                    elif frappe.utils.get_time(hours) < absent:
                        data["attendance"] = "Absent"

                """ Marking Late Checkin """
                if (
                    data["shift_start_time"]
                    and data["in_time"]
                    and data.get("in_date_time")
                    == first_checkin_by_date.get(format_date)
                    and format_date not in off_dates
                    and format_date not in attendance_request_dates
                ):
                    if str(data["date"]) > first_day_last_month:
                        late_entry_difference = (
                            data["in_time"] - data["shift_start_time"]
                        )
                        late_entry_difference_seconds = (
                            late_entry_difference.total_seconds()
                        )
                        f_seconds = (
                            fifteen_minutes_in.hour * 3600
                            + fifteen_minutes_in.minute * 60
                            + fifteen_minutes_in.second
                        )
                        is_half_day_late = (
                            half_day_late_threshold_seconds > 0
                            and late_entry_difference_seconds
                            >= half_day_late_threshold_seconds
                        )

                        if (
                            late_entry_difference_seconds > f_seconds
                            and not is_half_day_late
                        ):
                            data["late_entry"] = "Yes"
                            employee = str(data["employee"]) + str(data["date"])
                            if (
                                frappe.utils.format_time(late_entry_difference, "HH:mm")
                                != "00:00"
                            ):
                                late_entry_dict[format_date] = frappe.utils.format_time(
                                    late_entry_difference, "HH:mm"
                                )
                            if employee not in consecutive_late_entries:
                                consecutive_late_entries[employee] = (
                                    consecutive_late_entries.get(employee, 0) + 1
                                )
                                if len(consecutive_late_entries) > allowed_late_count:
                                    if (
                                        absent
                                        > frappe.utils.get_time(hours)
                                        > frappe.utils.get_time("00:00:00")
                                    ):
                                        data["attendance"] = "Absent"
                                    elif data["out_time"] is None and data["in_time"]:
                                        data["attendance"] = "Missing Out"
                                    else:
                                        data["attendance"] = "Half Day"
                        else:
                            data["late_entry"] = "No"

                """ Marking Early Checkout """

                if data["shift_end_time"] and data["out_time"]:
                    early_exit_difference = data["shift_end_time"] - data["out_time"]
                    early_exit_difference_seconds = (
                        early_exit_difference.total_seconds()
                    )
                    f_seconds = (
                        fifteen_minutes_out.hour * 3600
                        + fifteen_minutes_out.minute * 60
                        + fifteen_minutes_out.second
                    )
                    if early_exit_difference_seconds > f_seconds:
                        data["early_exit"] = "Yes"
                    else:
                        data["early_exit"] = "No"

                """Checking in area and out area"""
                if data["in_area"] and data["out_area"]:
                    if data["in_area"] != data["out_area"]:
                        data["area_change"] = "Yes"
                    if data["in_area"] == data["out_area"]:
                        data["area_change"] = "No"

                if (
                    first_day_last_month in late_entry_dict
                    or first_day_last_month in columns
                ):
                    late_entry_dict.remove(first_day_last_month)
                if first_day_next_month in late_entry_dict:
                    late_entry_dict.remove(first_day_next_month)
            late_count = len([key for key in late_entry_dict if "-" in str(key)])
            if late_count:
                late_entry_dict["late_count"] = late_count
                late_entry_dict["deduction_in_days"] = calculate_deduction_in_days(
                    late_count, allowed_late_count, deduction_cycle
                )
                result.append(late_entry_dict)

    return columns, result


def get_weekly_off_dates(weekly_holiday_list, from_date, to_date):
    if not weekly_holiday_list:
        return set()

    weekly_offs = frappe.db.get_all(
        "Weekly Off Holiday",
        filters={
            "parent": weekly_holiday_list,
            "parenttype": "Weekly Off List",
            "parentfield": "holidays",
            "holiday_date": ["between", [from_date, to_date]],
        },
        pluck="holiday_date",
    )

    return {str(frappe.utils.getdate(weekly_off)) for weekly_off in weekly_offs}


def get_holiday_dates(holiday_list, from_date, to_date):
    if not holiday_list:
        return set()

    holidays = frappe.db.get_all(
        "Holiday",
        filters={
            "parent": holiday_list,
            "parenttype": "Holiday List",
            "parentfield": "holidays",
            "holiday_date": ["between", [from_date, to_date]],
        },
        pluck="holiday_date",
    )

    return {str(frappe.utils.getdate(holiday)) for holiday in holidays}


def get_late_reversal_attendance_request_dates(employee, from_date, to_date):
    if not employee:
        return set()

    from_date = frappe.utils.getdate(from_date)
    to_date = frappe.utils.getdate(to_date)

    requests = frappe.db.sql(
        """
        SELECT
            from_date, to_date, half_day, half_day_date, custom_half_type
        FROM
            `tabAttendance Request`
        WHERE
            employee = %s
            AND docstatus = 1
            AND from_date <= %s
            AND to_date >= %s
            AND (status = 'Approved' OR workflow_state = 'Approved')
        """,
        (employee, to_date, from_date),
        as_dict=True,
    )

    reversal_dates = set()
    for request in requests:
        if request.get("half_day"):
            half_day_date = request.get("half_day_date")
            if (
                half_day_date
                and from_date <= frappe.utils.getdate(half_day_date) <= to_date
                and is_first_half(request.get("custom_half_type"))
            ):
                reversal_dates.add(str(frappe.utils.getdate(half_day_date)))
            continue

        current_date = max(frappe.utils.getdate(request.get("from_date")), from_date)
        request_to_date = min(frappe.utils.getdate(request.get("to_date")), to_date)
        while current_date <= request_to_date:
            reversal_dates.add(str(current_date))
            current_date = frappe.utils.add_to_date(current_date, days=1)

    return reversal_dates


def is_first_half(value):
    return (value or "").strip().lower().replace("_", " ") == "first half"


def calculate_deduction_in_days(late_count, allowed_late_count, deduction_cycle):
    if not deduction_cycle:
        return 0

    return max(((late_count - allowed_late_count) / deduction_cycle) / 2, 0)


def safe_get_time(value, default="00:00:00"):
    if value is None:
        value = default

    return frappe.utils.get_time(value)


def get_duration_seconds(value, default="00:00:00"):
    if value is None:
        value = default
    if hasattr(value, "total_seconds"):
        return value.total_seconds()
    if hasattr(value, "hour") and hasattr(value, "minute") and hasattr(value, "second"):
        return value.hour * 3600 + value.minute * 60 + value.second

    return frappe.utils.get_timedelta(str(value)).total_seconds()
