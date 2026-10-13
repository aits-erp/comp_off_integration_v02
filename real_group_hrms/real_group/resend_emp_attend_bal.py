import json
from collections import defaultdict

import frappe
from frappe.utils import now_datetime

from real_group_hrms.real_group.integration import oracle_connection


LEAVE_TYPE_MAP = {
    "PRESENT": "P",
    "ABSENT_LOP": "A",
    "HOLIDAY": "H",
    "NIGHT": "B",
    "TOUR": "T",
    "APPROVED_LEAVE": "M",
    "WEEKLY_OFF": "R",
    "OUTDOOR_DUTY_LEAVE": "O",
    "LATE_PENALTY": "N",
    "FULL_AND_FINAL_EARNING": "F",
    "FULL_AND_FINAL_DEDUCTION": "D",
    "EARNED_LEAVE": "E",
    "CASUAL_LEAVE": "L",
    "COMPENSATORY_OFF": "C",
    "SICK_LEAVE": "S",
    "ESIC_LEAVE": "I",
    "OPTIONAL_LEAVE": "X",
}

MONTH_NAMES = {
    1: "Jan",
    2: "Feb",
    3: "Mar",
    4: "Apr",
    5: "May",
    6: "Jun",
    7: "Jul",
    8: "Aug",
    9: "Sep",
    10: "Oct",
    11: "Nov",
    12: "Dec",
}


def _as_bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _as_list(value):
    if value in (None, "", []):
        return []

    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item]

    text_value = str(value).strip()
    if not text_value:
        return []

    if text_value.startswith("["):
        parsed = json.loads(text_value)
        return [str(item) for item in parsed if item]

    return [item.strip() for item in text_value.split(",") if item.strip()]


def _get_salary_slips(from_date, to_date, company=None, salary_slips=None, require_erp_vrno=True):
    filters = {
        "docstatus": 1,
        "start_date": [">=", from_date],
        "end_date": ["<=", to_date],
    }
    if company:
        filters["company"] = company
    if require_erp_vrno:
        filters["custom_erp_vrno"] = ["!=", ""]

    slips = frappe.get_all(
        "Salary Slip",
        filters=filters,
        fields=["name", "employee", "company", "custom_erp_vrno", "start_date", "end_date"],
        order_by="company asc, start_date asc, employee asc",
    )

    requested_slips = set(_as_list(salary_slips))
    if requested_slips:
        slips = [slip for slip in slips if slip.name in requested_slips]

    return slips


def _get_salary_slip_context(slip_name):
    return frappe.db.sql(
        """
        SELECT
            EXTRACT(YEAR FROM ss.start_date) AS cal_year,
            EXTRACT(MONTH FROM ss.end_date) AS month_no,
            UPPER(TRIM(TO_CHAR(ss.start_date, 'MON'))) AS month_char,
            ss.employee AS emp_code,
            ss.company,
            e.branch,
            e.custom_division AS division,
            e.department,
            ss.modified,
            (SELECT username FROM `tabUser` WHERE name = ss.owner) AS user_code,
            e.leave_approver AS leave_approver
        FROM `tabSalary Slip` ss
        LEFT JOIN `tabEmployee` e ON e.name = ss.employee
        WHERE ss.name = %s
        """,
        slip_name,
        as_dict=1,
    )[0]


def _get_report_filters(context):
    filters = {
        "month": MONTH_NAMES[context.month_no],
        "year": context.cal_year,
        "employee": context.emp_code,
        "company": context.company,
    }
    if context.branch:
        filters["branch"] = context.branch
    if context.division:
        filters["division"] = context.division
    if context.department:
        filters["department"] = context.department
    return filters


def _get_attendance_report_row(context):
    result = frappe.call(
        "frappe.desk.query_report.run",
        report_name="[New] Monthly Attendance Report",
        filters=_get_report_filters(context),
        ignore_prepared_report=True,
    )

    report_rows = (result or {}).get("result") or []
    if report_rows and isinstance(report_rows[0], dict):
        return next(
            (row for row in report_rows if row.get("employee") == context.emp_code),
            report_rows[0],
        )
    return {}


def _get_attendance_rows(slip_name):
    context = _get_salary_slip_context(slip_name)
    report_row = _get_attendance_report_row(context)

    mapped_values = {
        "PRESENT": report_row.get("total_present", 0.0),
        "ABSENT_LOP": (report_row.get("total_absent", 0.0) or 0.0)
        + (report_row.get("leave_without_pay", 0.0) or 0.0),
        "HOLIDAY": report_row.get("total_holiday_leave", 0.0),
        "OPTIONAL_LEAVE": report_row.get("optional_leave", 0.0),
        "SICK_LEAVE": report_row.get("sick_leave", 0.0),
        "ESIC_LEAVE": report_row.get("esic_leave", 0.0),
        "COMPENSATORY_OFF": report_row.get("total_compensatory_off", 0.0),
        "CASUAL_LEAVE": report_row.get("total_casual_leave", 0.0),
        "EARNED_LEAVE": report_row.get("total_earned_leave", 0.0),
        "NIGHT": report_row.get("night", 0.0),
        "APPROVED_LEAVE": report_row.get("approved_leave", 0.0),
        "WEEKLY_OFF": report_row.get("total_wo", 0.0),
        "OUTDOOR_DUTY_LEAVE": report_row.get("total_od", 0.0),
        "LATE_PENALTY": report_row.get("late_penalty", 0.0),
        "FULL_AND_FINAL_EARNING": report_row.get("full_and_final_earning", 0.0),
        "FULL_AND_FINAL_DEDUCTION": report_row.get("full_and_final_deduction", 0.0),
    }

    attendance_rows = []
    for leave_key, days in mapped_values.items():
        leave_type = leave_key.replace("_", " ").title()
        if frappe.db.exists("Leave Type", leave_type):
            attend_char = frappe.db.get_value("Leave Type", leave_type, "custom_erp_attend_char")
        else:
            attend_char = LEAVE_TYPE_MAP.get(leave_key)

        if attend_char:
            attendance_rows.append(
                {
                    "cal_year": str(context.cal_year),
                    "month": context.month_char,
                    "emp_code": context.emp_code,
                    "attend_char": attend_char,
                    "days": float(days or 0.0),
                    "user_code": context.user_code,
                    "lastupdate": context.modified,
                    "approvedby": context.leave_approver,
                    "approveddate": context.modified,
                }
            )

    return attendance_rows


def _get_execution_lastupdate():
    return now_datetime().replace(microsecond=0)


def resend_emp_attend_bal(
    from_date,
    to_date,
    company=None,
    salary_slips=None,
    dry_run=1,
    require_erp_vrno=1,
    current_lastupdate=1,
):
    dry_run = _as_bool(dry_run)
    require_erp_vrno = _as_bool(require_erp_vrno)
    current_lastupdate = _as_bool(current_lastupdate)
    execution_lastupdate = _get_execution_lastupdate() if current_lastupdate else None

    slips = _get_salary_slips(
        from_date=from_date,
        to_date=to_date,
        company=company,
        salary_slips=salary_slips,
        require_erp_vrno=require_erp_vrno,
    )

    summary = {
        "from_date": from_date,
        "to_date": to_date,
        "company": company,
        "dry_run": dry_run,
        "require_erp_vrno": require_erp_vrno,
        "current_lastupdate": current_lastupdate,
        "execution_lastupdate": str(execution_lastupdate) if execution_lastupdate else None,
        "salary_slips_found": len(slips),
        "employees_updated": len({slip.employee for slip in slips}),
        "companies_processed": 0,
        "slips_processed": 0,
        "rows_updated": 0,
        "rows_inserted": 0,
    }

    by_company = defaultdict(list)
    for slip in slips:
        by_company[slip.company].append(slip)

    for company_name, company_slips in by_company.items():
        con = oracle_connection(company_name)
        if not con:
            frappe.throw(f"Oracle connection failed for company '{company_name}'")

        cur = con.cursor()
        try:
            company_updated = 0
            company_inserted = 0

            for slip in company_slips:
                attendance_rows = _get_attendance_rows(slip.name)

                for row in attendance_rows:
                    if execution_lastupdate:
                        row["lastupdate"] = execution_lastupdate

                    cur.execute(
                        """
                        UPDATE RIPLRR.EMP_ATTEND_BAL
                        SET DAYS = :days,
                            USER_CODE = :user_code,
                            LASTUPDATE = :lastupdate,
                            APPROVEDBY = :approvedby,
                            APPROVEDDATE = :approveddate
                        WHERE CAL_YEAR = :cal_year
                          AND MONTH = :month
                          AND EMP_CODE = :emp_code
                          AND ATTEND_CHAR = :attend_char
                        """,
                        row,
                    )

                    if cur.rowcount == 0:
                        cur.execute(
                            """
                            INSERT INTO RIPLRR.EMP_ATTEND_BAL
                            (
                                CAL_YEAR,
                                MONTH,
                                EMP_CODE,
                                ATTEND_CHAR,
                                DAYS,
                                USER_CODE,
                                LASTUPDATE,
                                APPROVEDBY,
                                APPROVEDDATE
                            )
                            VALUES
                            (
                                :cal_year,
                                :month,
                                :emp_code,
                                :attend_char,
                                :days,
                                :user_code,
                                :lastupdate,
                                :approvedby,
                                :approveddate
                            )
                            """,
                            row,
                        )
                        company_inserted += 1
                    else:
                        company_updated += cur.rowcount

                summary["slips_processed"] += 1

            if dry_run:
                con.rollback()
            else:
                con.commit()

            summary["companies_processed"] += 1
            summary["rows_updated"] += company_updated
            summary["rows_inserted"] += company_inserted

        except Exception:
            con.rollback()
            raise
        finally:
            cur.close()
            con.close()

    return summary


def _format_execute_result(label, summary):
    action = "would update" if summary.get("dry_run") else "updated"
    return (
        f"{label}: {action} {summary.get('employees_updated', 0)} employees "
        f"across {summary.get('salary_slips_found', 0)} salary slips"
    )


def resend_emp_attend_bal_jan_2026(company=None, dry_run=0):
    summary = resend_emp_attend_bal(
        from_date="2026-01-01",
        to_date="2026-01-31",
        company=company,
        dry_run=dry_run,
        require_erp_vrno=1,
        current_lastupdate=1,
    )
    return _format_execute_result("January 2026", summary)


def resend_emp_attend_bal_feb_2026(company=None, dry_run=0):
    summary = resend_emp_attend_bal(
        from_date="2026-02-01",
        to_date="2026-02-28",
        company=company,
        dry_run=dry_run,
        require_erp_vrno=1,
        current_lastupdate=1,
    )
    return _format_execute_result("February 2026", summary)


def resend_emp_attend_bal_jan_feb_2026(company=None, dry_run=0):
    summary = resend_emp_attend_bal(
        from_date="2026-01-01",
        to_date="2026-02-28",
        company=company,
        dry_run=dry_run,
        require_erp_vrno=1,
        current_lastupdate=1,
    )
    return _format_execute_result("January-February 2026", summary)
