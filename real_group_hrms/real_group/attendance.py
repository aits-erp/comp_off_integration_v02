from datetime import datetime
from itertools import groupby
from operator import itemgetter

import frappe
from hrms.hr.doctype.leave_application.leave_application import get_leave_balance_on


@frappe.whitelist()
def reset_attendance_log(bio_id):
    frappe.db.sql(
        f"""
		UPDATE
			tabbioattendancelog
			set is_processed = 'N', message = null
		WHERE
			name = '{bio_id}'
	""",
        as_dict=True,
    )

    bio = frappe.db.sql("SELECT * from tabbioattendancelog where name = %s", bio_id)
    if bio:
        check_ins = frappe.db.get_all(
            "Employee Checkin", filters={"custom_bio_log_id": bio_id}
        )
        for check_in in check_ins:
            frappe.delete_doc("Employee Checkin", check_in.get("name"))

    frappe.db.commit()


@frappe.whitelist()
@frappe.whitelist()
def process_attendance_from_attendance_summary():
    all_employee = frappe.db.sql(
        """
		SELECT
			e.name
		FROM
			`tabEmployee` e
		LEFT JOIN
			`tabEmployee Grade` eg ON eg.name = e.grade
		WHERE
			status = 'Active'
			AND eg.custom_single_punch_applicable = 0
			AND eg.custom_no_punch_applicable = 0
	""",
        as_dict=1,
    )

    for emp in all_employee:
        frappe.enqueue(
            "real_group_hrms.real_group.attendance.process_attendance_from_attendance_summary_queue",
            queue="long",
            timeout=3600,
            employee=emp.name,
            company=emp.company,
        )


def process_attendance_from_attendance_summary_queue(employee, company):
    attendance_for_date = frappe.utils.add_to_date(frappe.utils.getdate(), days=-1)
    year = str(attendance_for_date.year)
    month = attendance_for_date.strftime("%b")
    month_number = datetime.strptime(month, "%b").month
    fr_date = datetime(int(year), month_number, 1).date()
    t_date = frappe.utils.add_to_date(frappe.utils.getdate(), days=-1)
    x = frappe.call(
        "frappe.desk.query_report.run",
        report_name="Biometric Attendance Summary To Mark Attendance",
        filters={
            "company": company,
            "branch": "",
            "month": month,
            "year": year,
            "employee": employee,
        },
        ignore_prepared_report=True,
    )
    filtered_result = []

    all_employee = frappe.db.sql(
        """
		SELECT
			e.name
		FROM
			`tabEmployee` e
		LEFT JOIN
			`tabEmployee Grade` eg ON eg.name = e.grade
		WHERE
			status = 'Active'
			AND eg.custom_single_punch_applicable = 0
			AND eg.custom_no_punch_applicable = 0
			AND e.name = %s
	""",
        employee,
        as_dict=1,
    )

    all_emp_list = {emp["name"] for emp in all_employee}

    emp_filter = set()
    if not x.get("result"):
        cur_date = fr_date
        emp_grade = frappe.db.get_value("Employee", employee, "grade")
        is_active = frappe.db.get_value("Employee", employee, "status")
        emp_grade_doc = frappe.get_doc("Employee Grade", emp_grade)
        date_of_joining = frappe.db.get_value("Employee", employee, "date_of_joining")
        if is_active == "Active":
            if (
                emp_grade_doc.custom_no_punch_applicable == 0
                or emp_grade_doc.custom_single_punch_applicable == 0
            ):
                while cur_date <= frappe.utils.getdate(
                    frappe.utils.add_to_date(frappe.utils.today(), days=-1)
                ):
                    holiday_sql = frappe.db.sql(
                        f"""
						SELECT
							h.name, h.holiday_date, h.weekly_off
						FROM
							`tabHoliday List` hl
						LEFT JOIN
							`tabHoliday` h ON hl.name = h.parent
						WHERE
							hl.name = '{frappe.db.get_value("Employee", employee, "holiday_list")}'
							AND h.holiday_date = '{cur_date}'
						GROUP BY
							h.holiday_date
					""",
                        as_dict=True,
                    )

                    # attendance_still_exists = frappe.db.get_all("Attendance", fields=["name"], filters={"employee": employee, "attendance_date": cur_date, "docstatus": "1"})

                    # frappe.log_error(f"N-{employee}-{cur_date}", {"attendance_exists": attendance_still_exists, "holiday_sql": holiday_sql,
                    # 												"date_of_joining": date_of_joining, "frappe.utils.getdate(frappe.utils.add_to_date(frappe.utils.today(), days=-1)": frappe.utils.getdate(frappe.utils.add_to_date(frappe.utils.today(), days=-1))})

                    attendance_exists = frappe.db.get_all(
                        "Attendance",
                        fields=["name"],
                        filters={
                            "employee": employee,
                            "attendance_date": cur_date,
                            "docstatus": "1",
                        },
                    )
                    if attendance_exists:
                        frappe.log_error("pass", employee)
                        for a in attendance_exists:
                            # att = frappe.get_doc("Attendance", a.get("name"))
                            # att.cancel()
                            # att.delete()
                            frappe.db.sql(
                                f"""
								DELETE
								FROM `tabAttendance`
								WHERE name = '{a.get("name")}'
							""",
                                as_dict=True,
                            )
                            frappe.db.commit()
                        if not holiday_sql:
                            if date_of_joining <= frappe.utils.getdate(
                                cur_date
                            ) and frappe.utils.getdate(
                                cur_date
                            ) <= frappe.utils.getdate(
                                frappe.utils.add_to_date(frappe.utils.today(), days=-1)
                            ):
                                attendance = frappe.new_doc("Attendance")
                                try:
                                    attendance.update(
                                        {
                                            "doctype": "Attendance",
                                            "employee": employee,
                                            "attendance_date": cur_date,
                                            "status": "Absent",
                                            "custom_attendance_tag": "No Punch Data",
                                            # "custom_half_type": half_type,
                                            # "custom_reason": r.get("attendance"),
                                            # "shift": r.get("shift"),
                                            # "late_entry": 1 if r.get("late_entry") == 'Yes' else 0,
                                            # "early_exit": 1 if r.get("early_exit") == 'Yes' else 0,
                                        }
                                    ).save()
                                    attendance.submit()
                                except Exception as e:
                                    msg = e
                                    frappe.log_error("attendance.py", msg)
                    else:
                        frappe.log_error("pass1", employee)
                        if not holiday_sql:
                            if date_of_joining <= frappe.utils.getdate(
                                cur_date
                            ) and frappe.utils.getdate(
                                cur_date
                            ) <= frappe.utils.getdate(
                                frappe.utils.add_to_date(frappe.utils.today(), days=-1)
                            ):
                                attendance = frappe.new_doc("Attendance")
                                try:
                                    attendance.update(
                                        {
                                            "doctype": "Attendance",
                                            "employee": employee,
                                            "attendance_date": cur_date,
                                            "status": "Absent",
                                            "custom_attendance_tag": "No Punch Data",
                                            # "custom_half_type": half_type,
                                            # "custom_reason": r.get("attendance"),
                                            # "shift": r.get("shift"),
                                            # "late_entry": 1 if r.get("late_entry") == 'Yes' else 0,
                                            # "early_exit": 1 if r.get("early_exit") == 'Yes' else 0,
                                        }
                                    ).save()
                                    attendance.submit()
                                except Exception as e:
                                    msg = e
                                    frappe.log_error("attendance.py", msg)
                    cur_date = frappe.utils.add_to_date(cur_date, days=1)
    else:
        for i in x.get("result"):
            frappe.log_error(
                f"attendance marking {i.get('employee')}", i.get("employee")
            )
            employee_code = i.get("employee")
            if employee_code in all_emp_list and employee_code not in emp_filter:
                emp_filter.add(employee_code)
            i["attendance_date"] = str(i.get("date"))
            if i["in_time"] is None and i["out_time"] is None:
                continue
            elif (
                i.get("attendance") == "Missing In and Out"
                or i.get("attendance") == "Not Present"
            ):
                continue
            elif i.get("attendance") == "" or i.get("attendance") is None:
                continue
            else:
                filtered_result.append(i)

        filtered_result.sort(key=itemgetter("employee"))

        for key, group in groupby(filtered_result, key=itemgetter("employee")):
            grouped = {}

            # Iterate over the current group of items for this employee
            for item in group:
                date = item.get("attendance_date")
                if date not in grouped:
                    grouped[date] = item

            inner_filtered_result = list(grouped.values())

            start_date = fr_date
            end_date = t_date

            missing_dates = []

            current_date = start_date
            while current_date <= end_date:
                missing_dates.append(
                    {
                        "attendance_date": str(current_date),
                        "attendance": "Absent",
                        "employee": key,
                    }
                )
                current_date += frappe.utils.get_timedelta("24:00:00")

            # Merge missing dates with filtered result for the current employee
            merged_dict = {
                item["attendance_date"]: item
                for item in missing_dates + inner_filtered_result
            }

            merged_list = list(merged_dict.values())
            mark_till = t_date
            for r in merged_list:
                cross_days = frappe.db.get_value(
                    "Shift Type", r.get("shift"), "custom_end_across_days"
                )
                if cross_days == 0:
                    mark_till = t_date
                if cross_days == 1:
                    mark_till = frappe.utils.add_to_date(t_date, days=-1)

                holiday_sql = frappe.db.sql(
                    f"""
					SELECT
						h.name, h.holiday_date, h.weekly_off
					FROM
						`tabHoliday List` hl
					LEFT JOIN
						`tabHoliday` h ON hl.name = h.parent
					WHERE
						hl.name = '{frappe.db.get_value("Employee", r.get("employee"), "holiday_list")}'
						AND h.holiday_date = '{r.get("attendance_date")}'
					GROUP BY
						h.holiday_date
				""",
                    as_dict=True,
                )

                attendance_tag = ""

                # if r.get("attendance") == 'POH' or r.get("attendance") == 'POW':
                # 	mark_attendance = 'Present'
                if r.get("attendance") is None or r.get("attendance") == "":
                    mark_attendance = "Absent"
                else:
                    mark_attendance = r.get("attendance")
                    # attendance_tag = "l"
                attendance_date = r.get("attendance_date")

                if holiday_sql and r.get("attendance") in (
                    "Present",
                    "Half Day",
                    "Absent",
                ):
                    if holiday_sql[0].weekly_off == 1:
                        attendance_tag = "POW"

                    if holiday_sql[0].weekly_off == 0:
                        attendance_tag = "POH"

                if r.get("attendance") in (
                    "Absent",
                    "Missing In",
                    "Missing Out",
                    "Invalid Punch",
                ):
                    mark_attendance = "Absent"
                    attendance_tag = ""

                half_type = ""
                if r.get("attendance") is not None:
                    if r.get("attendance") in ("Half Day"):
                        half_type = "First Half"
                        shift = frappe.get_doc("Shift Type", r.get("shift"))
                        half_day_time = (
                            shift.start_time + shift.custom_half_day_threshold
                        )

                        if r.get("in_time") > half_day_time:
                            half_type = "Second Half"

                attendance_exists = frappe.db.get_all(
                    "Attendance",
                    fields=["name"],
                    filters={
                        "employee": r.get("employee"),
                        "attendance_date": r.get("attendance_date"),
                        "docstatus": "1",
                    },
                )
                # for a in attendance_exists:
                # 	att = frappe.get_doc("Attendance", a.get("name"))
                # 	att.cancel()
                # 	att.delete()
                if mark_attendance == "Absent":
                    frappe.log_error(
                        f"P-{r.get('employee')}-{attendance_date}",
                        {
                            "shift": r.get("shift"),
                            "fr_date": fr_date,
                            "t_date": t_date,
                            "mark_till": mark_till,
                            "mark_attendance": mark_attendance,
                            "r.get(attendance)": r.get("attendance"),
                            "merged_list": merged_list,
                        },
                    )
                if not attendance_exists:
                    if not holiday_sql or (
                        mark_attendance in ("Half Day", "Present")
                        and attendance_tag not in ("POH", "POW")
                    ):
                        if frappe.utils.getdate(
                            attendance_date
                        ) <= frappe.utils.getdate(mark_till):
                            attendance = frappe.new_doc("Attendance")
                            try:
                                attendance.update(
                                    {
                                        "doctype": "Attendance",
                                        "employee": r.get("employee"),
                                        "attendance_date": attendance_date,
                                        "status": mark_attendance,
                                        "custom_attendance_tag": attendance_tag,
                                        "custom_half_type": half_type,
                                        "custom_reason": r.get("attendance"),
                                        "shift": r.get("shift"),
                                        "late_entry": (
                                            1 if r.get("late_entry") == "Yes" else 0
                                        ),
                                        "early_exit": (
                                            1 if r.get("early_exit") == "Yes" else 0
                                        ),
                                    }
                                ).save()
                                attendance.submit()
                            except Exception as e:
                                frappe.log_error("attendance.py line 606", e)


@frappe.whitelist()
def process_attendance_for_last_day_of_month():
    all_employee = frappe.db.sql(
        """
		SELECT
			e.name
		FROM
			`tabEmployee` e
		LEFT JOIN
			`tabEmployee Grade` eg ON eg.name = e.grade
		WHERE
			status = 'Active'
			AND eg.custom_single_punch_applicable = 0
			AND eg.custom_no_punch_applicable = 0
	""",
        as_dict=1,
    )

    for emp in all_employee:
        frappe.enqueue(
            "real_group_hrms.real_group.attendance.process_attendance_for_last_day_of_month_queue",
            queue="long",
            timeout=3600,
            employee=emp.name,
            company=emp.company,
        )


def process_attendance_for_last_day_of_month_queue(employee, company):
    attendance_for_date = frappe.utils.add_to_date(frappe.utils.getdate(), days=-2)
    year = str(attendance_for_date.year)
    month = attendance_for_date.strftime("%b")
    month_number = datetime.strptime(month, "%b").month
    fr_date = datetime(int(year), month_number, 1).date()
    t_date = frappe.utils.add_to_date(frappe.utils.getdate(), days=-2)
    x = frappe.call(
        "frappe.desk.query_report.run",
        report_name="Biometric Attendance Summary To Mark Attendance",
        filters={
            "company": company,
            "branch": "",
            "month": month,
            "year": year,
            "employee": employee,
        },
        ignore_prepared_report=True,
    )
    filtered_result = []

    all_employee = frappe.db.sql(
        """
		SELECT
			e.name
		FROM
			`tabEmployee` e
		LEFT JOIN
			`tabEmployee Grade` eg ON eg.name = e.grade
		WHERE
			status = 'Active'
			AND eg.custom_single_punch_applicable = 0
			AND eg.custom_no_punch_applicable = 0
			AND e.name = %s
	""",
        employee,
        as_dict=1,
    )

    all_emp_list = {emp["name"] for emp in all_employee}

    emp_filter = set()
    if not x.get("result"):
        cur_date = fr_date
        emp_grade = frappe.db.get_value("Employee", employee, "grade")
        is_active = frappe.db.get_value("Employee", employee, "status")
        emp_grade_doc = frappe.get_doc("Employee Grade", emp_grade)
        date_of_joining = frappe.db.get_value("Employee", employee, "date_of_joining")
        if is_active == "Active":
            if (
                emp_grade_doc.custom_no_punch_applicable == 0
                or emp_grade_doc.custom_single_punch_applicable == 0
            ):
                while cur_date <= frappe.utils.getdate(
                    frappe.utils.add_to_date(frappe.utils.today(), days=-2)
                ):
                    attendance_exists = frappe.db.get_all(
                        "Attendance",
                        fields=["name"],
                        filters={
                            "employee": employee,
                            "attendance_date": cur_date,
                            "docstatus": "1",
                        },
                    )
                    holiday_sql = frappe.db.sql(
                        f"""
						SELECT
							h.name, h.holiday_date, h.weekly_off
						FROM
							`tabHoliday List` hl
						LEFT JOIN
							`tabHoliday` h ON hl.name = h.parent
						WHERE
							hl.name = '{frappe.db.get_value("Employee", employee, "holiday_list")}'
							AND h.holiday_date = '{cur_date}'
						GROUP BY
							h.holiday_date
					""",
                        as_dict=True,
                    )

                    # for a in attendance_exists:
                    # 	att = frappe.get_doc("Attendance", a.get("name"))
                    # 	att.cancel()
                    # 	att.delete()
                    if not attendance_exists:
                        if not holiday_sql:
                            if date_of_joining <= frappe.utils.getdate(
                                cur_date
                            ) and frappe.utils.getdate(
                                cur_date
                            ) <= frappe.utils.getdate(
                                frappe.utils.add_to_date(frappe.utils.today(), days=-2)
                            ):
                                attendance = frappe.new_doc("Attendance")
                                try:
                                    attendance.update(
                                        {
                                            "doctype": "Attendance",
                                            "employee": employee,
                                            "attendance_date": cur_date,
                                            "status": "Absent",
                                            "custom_attendance_tag": "No Punch Data",
                                            # "custom_half_type": half_type,
                                            # "custom_reason": r.get("attendance"),
                                            # "shift": r.get("shift"),
                                            # "late_entry": 1 if r.get("late_entry") == 'Yes' else 0,
                                            # "early_exit": 1 if r.get("early_exit") == 'Yes' else 0,
                                        }
                                    ).save()
                                    attendance.submit()
                                except Exception as e:
                                    msg = e
                                    frappe.log_error("attendance.py", msg)
                    cur_date = frappe.utils.add_to_date(cur_date, days=1)
    else:
        for i in x.get("result"):
            employee_code = i.get("employee")
            if employee_code in all_emp_list and employee_code not in emp_filter:
                emp_filter.add(employee_code)
            i["attendance_date"] = str(i.get("date"))
            if i["in_time"] is None and i["out_time"] is None:
                continue
            elif (
                i.get("attendance") == "Missing In and Out"
                or i.get("attendance") == "Not Present"
            ):
                continue
            elif i.get("attendance") == "" or i.get("attendance") is None:
                continue
            else:
                filtered_result.append(i)

        filtered_result.sort(key=itemgetter("employee"))

        for key, group in groupby(filtered_result, key=itemgetter("employee")):
            grouped = {}

            # Iterate over the current group of items for this employee
            for item in group:
                date = item.get("attendance_date")
                if date not in grouped:
                    grouped[date] = item

            inner_filtered_result = list(grouped.values())

            start_date = fr_date
            end_date = t_date

            missing_dates = []

            current_date = start_date
            while current_date <= end_date:
                missing_dates.append(
                    {
                        "attendance_date": str(current_date),
                        "attendance": "Absent",
                        "employee": key,
                    }
                )
                current_date += frappe.utils.get_timedelta("24:00:00")

            # Merge missing dates with filtered result for the current employee
            merged_dict = {
                item["attendance_date"]: item
                for item in missing_dates + inner_filtered_result
            }

            merged_list = list(merged_dict.values())
            mark_till = t_date  # noqa: F841
            date_of_joining = frappe.db.get_value("Employee", key, "date_of_joining")
            for r in merged_list:
                holiday_sql = frappe.db.sql(
                    f"""
					SELECT
						h.name, h.holiday_date, h.weekly_off
					FROM
						`tabHoliday List` hl
					LEFT JOIN
						`tabHoliday` h ON hl.name = h.parent
					WHERE
						hl.name = '{frappe.db.get_value("Employee", r.get("employee"), "holiday_list")}'
						AND h.holiday_date = '{r.get("attendance_date")}'
					GROUP BY
						h.holiday_date
				""",
                    as_dict=True,
                )

                attendance_tag = ""

                # if r.get("attendance") == 'POH' or r.get("attendance") == 'POW':
                # 	mark_attendance = 'Present'
                if r.get("attendance") is None or r.get("attendance") == "":
                    mark_attendance = "Absent"
                else:
                    mark_attendance = r.get("attendance")
                    # attendance_tag = "l"
                attendance_date = r.get("attendance_date")

                if holiday_sql and r.get("attendance") in (
                    "Present",
                    "Half Day",
                    "Absent",
                ):
                    if holiday_sql[0].weekly_off == 1:
                        attendance_tag = "POW"

                    if holiday_sql[0].weekly_off == 0:
                        attendance_tag = "POH"

                if r.get("attendance") in (
                    "Absent",
                    "Missing In",
                    "Missing Out",
                    "Invalid Punch",
                ):
                    mark_attendance = "Absent"
                    attendance_tag = ""

                half_type = ""
                if r.get("attendance") is not None:
                    if r.get("attendance") in ("Half Day"):
                        half_type = "First Half"
                        shift = frappe.get_doc("Shift Type", r.get("shift"))
                        half_day_time = (
                            shift.start_time + shift.custom_half_day_threshold
                        )

                        if r.get("in_time") > half_day_time:
                            half_type = "Second Half"

                attendance_exists = frappe.db.get_all(
                    "Attendance",
                    fields=["name"],
                    filters={
                        "employee": r.get("employee"),
                        "attendance_date": r.get("attendance_date"),
                        "docstatus": "1",
                    },
                )
                # for a in attendance_exists:
                # 	att = frappe.get_doc("Attendance", a.get("name"))
                # 	att.cancel()
                # 	att.delete()
                if not attendance_exists:
                    if not holiday_sql or (
                        mark_attendance in ("Half Day", "Present")
                        and attendance_tag not in ("POH", "POW")
                    ):
                        if frappe.utils.getdate(
                            attendance_date
                        ) <= frappe.utils.getdate(
                            frappe.utils.add_to_date(frappe.utils.getdate(), days=-2)
                        ) and (
                            not date_of_joining
                            or frappe.utils.getdate(attendance_date)
                            >= frappe.utils.getdate(date_of_joining)
                        ):
                            attendance = frappe.new_doc("Attendance")
                            try:
                                attendance.update(
                                    {
                                        "doctype": "Attendance",
                                        "employee": r.get("employee"),
                                        "attendance_date": attendance_date,
                                        "status": mark_attendance,
                                        "custom_attendance_tag": attendance_tag,
                                        "custom_half_type": half_type,
                                        "custom_reason": r.get("attendance"),
                                        "shift": r.get("shift"),
                                        "late_entry": (
                                            1 if r.get("late_entry") == "Yes" else 0
                                        ),
                                        "early_exit": (
                                            1 if r.get("early_exit") == "Yes" else 0
                                        ),
                                    }
                                ).save()
                                attendance.submit()
                            except Exception as e:
                                frappe.log_error("attendance.py line 606", e)


# ### Modified Code

# def terminate_leave_allocation_on_expiry():
# 	today = frappe.utils.add_to_date(frappe.utils.getdate(), days=-1)
# 	# comp_lv_req = frappe.db.get_all("Compensatory Leave Request", filters={"expiry": today, "docstatus": 1})
# 	comp_lv_req = frappe.db.get_all("Compensatory Leave Request", filters={"expiry": ["<=", today], "docstatus": 1, "custom_is_expired": 0, "custom_utilised": 0, "employee": 50075}, fields=["name", "custom_balance", "leave_allocation"])
# 	print(comp_lv_req)
# 	if comp_lv_req:
# 		for count in comp_lv_req:
# 			if count.get("custom_balance") > 0:
# 				al = frappe.get_doc("Leave Allocation", count.get("leave_allocation"))
# 				al.new_leaves_allocated = al.new_leaves_allocated - count.get("custom_balance")
# 				al.total_leaves_allocated = al.total_leaves_allocated - count.get("custom_balance")
# 				al.save()
# 				frappe.db.set_value("Compensatory Leave Request", count.get("name"), "custom_is_expired", 1)
# 				frappe.db.set_value("Compensatory Leave Request", count.get("name"), "custom_expired_leaves", count.get("custom_balance"))


## Original Code


def terminate_leave_allocation_on_expiry():
    today = frappe.utils.add_to_date(frappe.utils.getdate(), days=-1)
    comp_lv_req = frappe.db.get_all(
        "Compensatory Leave Request", filters={"expiry": today, "docstatus": 1}
    )
    print(comp_lv_req)
    if comp_lv_req:
        for count in comp_lv_req:
            comp_leave = frappe.get_doc("Compensatory Leave Request", count.get("name"))
            allocated_leave_list = frappe.db.get_all(
                "Leave Allocation",
                filters={
                    "leave_type": "Compensatory Off",
                    "employee": comp_leave.employee,
                },
            )
            if allocated_leave_list:
                al = frappe.get_doc(
                    "Leave Allocation", allocated_leave_list[0].get("name")
                )
                leave_balance = get_leave_balance_on(
                    comp_leave.employee,
                    comp_leave.leave_type,
                    frappe.utils.add_to_date(frappe.utils.today(), days=-1),
                    frappe.utils.add_to_date(frappe.utils.today(), days=-1),
                    consider_all_leaves_in_the_allocation_period=True,
                    for_consumption=True,
                )
                difference = al.new_leaves_allocated - comp_leave.credit
                if difference >= (
                    leave_balance.get("leave_balance") - comp_leave.credit
                ):
                    try:
                        al.new_leaves_allocated = (
                            al.new_leaves_allocated - comp_leave.credit
                        )
                        al.total_leaves_allocated = (
                            al.total_leaves_allocated - comp_leave.credit
                        )
                        al.save()
                        frappe.db.set_value(
                            "Compensatory Leave Request",
                            comp_leave.name,
                            "custom_is_expired",
                            1,
                        )
                    except Exception as e:
                        frappe.log_error("terminate_leave_allocation_on_expiry", e)
