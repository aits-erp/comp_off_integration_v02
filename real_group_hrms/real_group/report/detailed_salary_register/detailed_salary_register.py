from importlib import import_module

import frappe
from frappe.utils import flt, get_last_day, getdate

from real_group_hrms.overrides.query_report_export import set_xlsx_cell_style_like_header

# IMPORTANT: module path contains [new]_form_14 so normal import won't work
new_form_14 = import_module("real_group_hrms.real_group.report.[new]_form_14.[new]_form_14")


# ----------------  Salary Component Order ----------------

HR_ALLOTTED_ORDER = [
    "Basic",
    "House Rent Allowance",
    "Conveyance",
    "Education Allowance",
    "Canteen Allowance",
    "Washing Allowance",
    "Special Allowances",
    "Children Hostel Allowance",
    "Over Time",
    "Incentives",
    "Local Transport Allowance",
    "Miscellaneous",
]

HR_ACTUAL_ORDER = [
    "Basic",
    "House Rent Allowance",
    "Conveyance",
    "Education Allowance",
    "Canteen Allowance",
    "Washing Allowance",
    "Special Allowances",
    "Children Hostel Allowance",
]

REPORT_DATE_FORMAT = "%d/%m/%Y"


# ---------------- Public API ----------------
def execute(filters=None):
    filters = frappe._dict(filters or {})

    if not (filters.get("company") and filters.get("month") and filters.get("year")):
        return [], []

    columns = get_columns(filters)
    data = get_data(filters, columns)
    return columns, data


# ---------------- Columns (ordered) ----------------
def get_columns(filters=None):
    filters = frappe._dict(filters or {})

    if filters.get("summarized_view"):
        return get_summary_columns()

    return get_detailed_columns()


def get_detailed_columns():
    # Base columns (same as your sandbox)
    base_cols = [
        {
            "fieldname": "salary_slip",
            "fieldtype": "Data",
            "label": "Salary Slip ID",
            "width": "150px",
        },
        {
            "fieldname": "emp",
            "fieldtype": "Data",
            "label": "Employee",
            "width": "150px",
        },
        {
            "fieldname": "emp_name",
            "fieldtype": "Data",
            "label": "Employee Name",
            "width": "150px",
        },
        {
            "fieldname": "father_name",
            "fieldtype": "Data",
            "label": "Father Name",
            "width": "150px",
        },
        {
            "fieldname": "emp_category",
            "fieldtype": "Data",
            "label": "Category",
            "width": "150px",
        },
        {
            "fieldname": "designation",
            "fieldtype": "Data",
            "label": "Designation",
            "width": "150px",
        },
        {
            "fieldname": "department",
            "fieldtype": "Data",
            "label": "Department",
            "width": "150px",
        },
        {
            "fieldname": "division",
            "fieldtype": "Data",
            "label": "Division",
            "width": "150px",
        },
        {
            "fieldname": "company",
            "fieldtype": "Data",
            "label": "Company",
            "width": "150px",
        },
        {
            "fieldname": "date_of_birth",
            "fieldtype": "Data",
            "label": "Date of Birth",
            "width": "150px",
        },
        {
            "fieldname": "date_of_joining",
            "fieldtype": "Data",
            "label": "Date of Joining",
            "width": "150px",
        },
        {
            "fieldname": "bank_name",
            "fieldtype": "Data",
            "label": "Bank",
            "width": "150px",
        },
        {
            "fieldname": "bank_ac_no",
            "fieldtype": "Data",
            "label": "Bank Account",
            "width": "150px",
        },
        {
            "fieldname": "ifsc_code",
            "fieldtype": "Data",
            "label": "IFSC Code",
            "width": "150px",
        },
        {
            "fieldname": "branch",
            "fieldtype": "Data",
            "label": "Branch",
            "width": "150px",
        },
        {
            "fieldname": "gross",
            "fieldtype": "Float",
            "precision": "0",
            "label": "Gross",
            "width": "150px",
        },
        {
            "fieldname": "paid_days",
            "fieldtype": "Float",
            "precision": "1",
            "label": "Paid Days",
            "width": "150px",
        },
        {
            "fieldname": "present_real",
            "fieldtype": "Float",
            "precision": "1",
            "label": "Present Days",
            "width": "150px",
        },
        {
            "fieldname": "absent",
            "fieldtype": "Float",
            "precision": "1",
            "label": "Absent",
            "width": "150px",
        },
        {
            "fieldname": "casual_leave",
            "fieldtype": "Float",
            "precision": "1",
            "label": "CL",
            "width": "150px",
        },
        {
            "fieldname": "earned_leave",
            "fieldtype": "Float",
            "precision": "1",
            "label": "EL",
            "width": "150px",
        },
        {
            "fieldname": "comp_off",
            "fieldtype": "Float",
            "precision": "1",
            "label": "C-Off",
            "width": "150px",
        },
        {
            "fieldname": "tour_for_office",
            "fieldtype": "Float",
            "precision": "1",
            "label": "Tour for Office",
            "width": "150px",
        },
        {
            "fieldname": "od",
            "fieldtype": "Float",
            "precision": "1",
            "label": "OD",
            "width": "150px",
        },
        {
            "fieldname": "weekly_off",
            "fieldtype": "Float",
            "precision": "1",
            "label": "Weekly Off",
            "width": "150px",
        },
        {
            "fieldname": "holiday",
            "fieldtype": "Float",
            "precision": "1",
            "label": "Holiday",
            "width": "150px",
        },
        {
            "fieldname": "month_days",
            "fieldtype": "Float",
            "precision": "1",
            "label": "Month Days",
            "width": "150px",
        },
        {
            "fieldname": "loan_opening_balance",
            "fieldtype": "Float",
            "precision": "0",
            "label": "Loan Opening Balance",
            "width": "150px",
        },
        {
            "fieldname": "amount_to_deduct",
            "fieldtype": "Float",
            "precision": "0",
            "label": "Amount To Deduct",
            "width": "150px",
        },
        {
            "fieldname": "deducted_amount",
            "fieldtype": "Float",
            "precision": "0",
            "label": "Deducted Amount",
            "width": "150px",
        },
        {
            "fieldname": "loan_closing",
            "fieldtype": "Float",
            "precision": "0",
            "label": "Loan Closing",
            "width": "150px",
        },
    ]

    # Component field mapping (your fixed fields)
    # You can add more mappings if new components exist later.
    allotted_map = {
        "Basic": ("earned_basic_alotted", "Basic"),
        "Conveyance": ("conveyance_alotted", "Conveyance"),
        "Canteen Allowance": ("canteen_allowance_alotted", "Canteen Allowance"),
        "Children Hostel Allowance": (
            "children_allowance_alotted",
            "Children Allowance",
        ),
        "Education Allowance": ("education_allowance_alotted", "Education Allowance"),
        "House Rent Allowance": (
            "house_rent_allowance_alotted",
            "House Rent Allowance",
        ),
        "Special Allowances": ("special_pay_alotted", "Special Pay"),
        "Washing Allowance": ("washing_allowance_alotted", "Washing Allowance"),
        "Over Time": ("over_time_alotted", "Over Time"),
        "Incentives": ("incentive_alotted", "Incentive"),
        "Local Transport Allowance": (
            "transport_allowance_alotted",
            "Transport Allowance",
        ),
        "Miscellaneous": ("misc_alotted", "MISC"),
    }

    actual_map = {
        "Basic": ("earned_basic_actual", "E_BASIC"),
        "House Rent Allowance": ("house_rent_allowance_actual", "HRA"),
        "Conveyance": ("conveyance_actual", "C_REIM"),
        "Education Allowance": ("education_allowance_actual", "EDU"),
        "Canteen Allowance": ("canteen_allowance_actual", "CANTEEN"),
        "Washing Allowance": ("washing_allowance_actual", "WASH"),
        "Special Allowances": ("special_pay_actual", "SPECIAL"),
        "Children Hostel Allowance": ("children_allowance_actual", "CHILD"),
    }

    # Build allotted columns
    allotted_cols = []
    for comp in HR_ALLOTTED_ORDER:
        if comp in allotted_map:
            fieldname, label = allotted_map[comp]
            allotted_cols.append(
                {
                    "fieldname": fieldname,
                    "fieldtype": "Float",
                    "precision": "0",
                    "label": label,
                    "width": "150px",
                }
            )

    allotted_cols.append(
        {
            "fieldname": "gross_pay_alotted",
            "fieldtype": "Float",
            "precision": "0",
            "label": "Gross Pay",
            "width": "150px",
        }
    )

    # Build actual columns
    actual_cols = []
    used = set()
    for comp in HR_ACTUAL_ORDER:
        if comp in actual_map:
            fieldname, label = actual_map[comp]
            actual_cols.append(
                {
                    "fieldname": fieldname,
                    "fieldtype": "Float",
                    "precision": "0",
                    "label": label,
                    "width": "150px",
                }
            )
            used.add(comp)

    for comp, (fieldname, label) in actual_map.items():
        if comp not in used:
            actual_cols.append(
                {
                    "fieldname": fieldname,
                    "fieldtype": "Float",
                    "precision": "0",
                    "label": label,
                    "width": "150px",
                }
            )

    # Remaining fixed tail columns (same as your sandbox)
    tail_cols = [
        {
            "fieldname": "gross_pay_actual",
            "fieldtype": "Float",
            "precision": "0",
            "label": "EARNED GROSS",
            "width": "150px",
        },
        {
            "fieldname": "over_time_actual",
            "fieldtype": "Float",
            "precision": "0",
            "label": "OT",
            "width": "120px",
        },
        {
            "fieldname": "incentive_actual",
            "fieldtype": "Float",
            "precision": "0",
            "label": "INCT",
            "width": "120px",
        },
        {
            "fieldname": "gross_pay_total_earned",
            "fieldtype": "Float",
            "precision": "0",
            "label": "EARNED TOTAL",
            "width": "150px",
        },
        {
            "fieldname": "employee_provident_fund",
            "fieldtype": "Float",
            "precision": "0",
            "label": "EPF",
            "width": "120px",
        },
        {
            "fieldname": "esic",
            "fieldtype": "Float",
            "precision": "0",
            "label": "ESIC",
            "width": "120px",
        },
        {
            "fieldname": "loan",
            "fieldtype": "Float",
            "precision": "0",
            "label": "LOAN",
            "width": "120px",
        },
        {
            "fieldname": "salary_advance",
            "fieldtype": "Float",
            "precision": "0",
            "label": "ADV",
            "width": "120px",
        },
        {
            "fieldname": "income_tax",
            "fieldtype": "Float",
            "precision": "0",
            "label": "IT",
            "width": "120px",
        },
        {
            "fieldname": "nps",
            "fieldtype": "Float",
            "precision": "0",
            "label": "NPS",
            "width": "120px",
        },
        {
            "fieldname": "misc_actual",
            "fieldtype": "Float",
            "precision": "0",
            "label": "MISC",
            "width": "120px",
        },
        {
            "fieldname": "labour_welfare_fund",
            "fieldtype": "Float",
            "precision": "0",
            "label": "LWF",
            "width": "120px",
        },
        {
            "fieldname": "other_ded",
            "fieldtype": "Float",
            "precision": "0",
            "label": "OTHER DED",
            "width": "140px",
        },
        {
            "fieldname": "glwf",
            "fieldtype": "Float",
            "precision": "0",
            "label": "GLWF",
            "width": "120px",
        },
        {
            "fieldname": "total_deduction",
            "fieldtype": "Float",
            "precision": "0",
            "label": "DTOT",
            "width": "120px",
        },
        {
            "fieldname": "net_payment",
            "fieldtype": "Float",
            "precision": "0",
            "label": "NET PAYMENT",
            "width": "150px",
        },
        {
            "fieldname": "remark",
            "fieldtype": "Data",
            "label": "REMARK",
            "width": "150px",
        },
    ]

    return base_cols + allotted_cols + actual_cols + tail_cols


def get_summary_columns():
    return [
        {
            "fieldname": "division",
            "fieldtype": "Data",
            "label": "DIVISION",
            "width": "220px",
        },
        {
            "fieldname": "manpower",
            "fieldtype": "Int",
            "label": "MP",
            "width": "80px",
        },
        {
            "fieldname": "gross",
            "fieldtype": "Float",
            "precision": "0",
            "label": "GROSS",
            "width": "120px",
        },
        {
            "fieldname": "paid_days",
            "fieldtype": "Float",
            "precision": "1",
            "label": "PD",
            "width": "90px",
        },
        {
            "fieldname": "earned_basic_actual",
            "fieldtype": "Float",
            "precision": "0",
            "label": "E_BASIC",
            "width": "120px",
        },
        {
            "fieldname": "gross_pay_total_earned",
            "fieldtype": "Float",
            "precision": "0",
            "label": "EARNED TOTAL",
            "width": "140px",
        },
        {
            "fieldname": "employee_provident_fund",
            "fieldtype": "Float",
            "precision": "0",
            "label": "EPF",
            "width": "100px",
        },
        {
            "fieldname": "esic",
            "fieldtype": "Float",
            "precision": "0",
            "label": "ESIC",
            "width": "90px",
        },
        {
            "fieldname": "loan",
            "fieldtype": "Float",
            "precision": "0",
            "label": "LOAN",
            "width": "100px",
        },
        {
            "fieldname": "salary_advance",
            "fieldtype": "Float",
            "precision": "0",
            "label": "ADV",
            "width": "90px",
        },
        {
            "fieldname": "income_tax",
            "fieldtype": "Float",
            "precision": "0",
            "label": "IT",
            "width": "90px",
        },
        {
            "fieldname": "nps",
            "fieldtype": "Float",
            "precision": "0",
            "label": "NPS",
            "width": "90px",
        },
        {
            "fieldname": "misc_actual",
            "fieldtype": "Float",
            "precision": "0",
            "label": "MISC",
            "width": "90px",
        },
        {
            "fieldname": "labour_welfare_fund",
            "fieldtype": "Float",
            "precision": "0",
            "label": "LWF",
            "width": "90px",
        },
        {
            "fieldname": "other_ded",
            "fieldtype": "Float",
            "precision": "0",
            "label": "OTH DED",
            "width": "110px",
        },
        {
            "fieldname": "glwf",
            "fieldtype": "Float",
            "precision": "0",
            "label": "GLWF",
            "width": "90px",
        },
        {
            "fieldname": "total_deduction",
            "fieldtype": "Float",
            "precision": "0",
            "label": "DTOT",
            "width": "110px",
        },
        {
            "fieldname": "net_payment",
            "fieldtype": "Float",
            "precision": "0",
            "label": "NET PAYMENT",
            "width": "140px",
        },
        {
            "fieldname": "remark",
            "fieldtype": "Data",
            "label": "REMARK",
            "width": "140px",
        },
    ]


# ---------------- Data ----------------
def get_data(filters, columns=None):
    columns = columns or get_columns(filters)

    year = filters.get("year")
    month = filters.get("month")
    employee = filters.get("employee")
    company = filters.get("company")
    branch = filters.get("branch")
    division = filters.get("division")
    department = filters.get("department")

    from_date, to_date = get_month_range(year, month)
    precision_map = get_column_precision_map(columns)

    # Build WHERE safely
    where = ["1=1", "ss.docstatus <> 2"]
    params = {"from_date": from_date, "to_date": to_date}

    if employee:
        where.append("e.name = %(employee)s")
        params["employee"] = employee
    where.append("e.company = %(company)s")
    params["company"] = company

    if branch:
        where.append("e.branch = %(branch)s")
        params["branch"] = branch
    if division:
        where.append("e.custom_division = %(division)s")
        params["division"] = division
    if department:
        where.append("e.department = %(department)s")
        params["department"] = department

    where_sql = " AND ".join(where)

    # Use the structure stored on the slip when available. This preserves the exact
    # structure used to generate the slip and avoids missing mid-month joiners whose
    # assignment starts after the slip start date.
    sql = frappe.db.sql(
        f"""
        SELECT
            ss.name as salary_slip,
            e.name as emp,
            e.employee_name as emp_name,
            e.custom_father_name as father_name,
            e.first_name,
            e.date_of_birth,
            e.date_of_joining,
            e.branch,
            e.custom_emp_category emp_category,
            e.department,
            e.custom_division division,
            e.designation,
            e.bank_name,
            e.bank_ac_no,
            e.ifsc_code,
            e.company,
            e.holiday_list,

            st.total_earning as gross_pay_alotted,
            COALESCE(ss.salary_structure, ssa.salary_structure) as sst_name,

            ss.payment_days as paid_days,
            (ss.leave_without_pay + ss.absent_days) absent,
            ss.total_working_days as month_days,

            MAX(CASE WHEN sd.salary_component = 'Basic' THEN sd.amount ELSE 0 END) as earned_basic_actual,
            ROUND(MAX(CASE WHEN sd.salary_component = 'Conveyance' THEN sd.amount ELSE 0 END), 0) conveyance_actual,
            MAX(CASE WHEN sd.salary_component = 'Canteen Allowance' THEN sd.amount ELSE 0 END) canteen_allowance_actual,
            MAX(CASE WHEN sd.salary_component = 'Children Hostel Allowance' THEN sd.amount ELSE 0 END) children_allowance_actual,
            MAX(CASE WHEN sd.salary_component = 'Education Allowance' THEN sd.amount ELSE 0 END) education_allowance_actual,
            MAX(CASE WHEN sd.salary_component = 'House Rent Allowance' THEN sd.amount ELSE 0 END) house_rent_allowance_actual,
            MAX(CASE WHEN sd.salary_component = 'Special Allowances' THEN sd.amount ELSE 0 END) special_pay_actual,
            MAX(CASE WHEN sd.salary_component = 'Washing Allowance' THEN sd.amount ELSE 0 END) washing_allowance_actual,
            MAX(CASE WHEN sd.salary_component = 'Over Time' THEN sd.amount ELSE 0 END) over_time_actual,
            MAX(CASE WHEN sd.salary_component = 'Incentives' THEN sd.amount ELSE 0 END) incentive_actual,
            MAX(CASE WHEN sd.salary_component = 'Local Transport Allowance' THEN sd.amount ELSE 0 END) transport_allowance_actual,
            MAX(CASE WHEN sd.salary_component = 'Miscellaneous' THEN sd.amount ELSE 0 END) misc_actual,
            MAX(CASE WHEN sd.salary_component = 'Provident Fund' THEN sd.amount ELSE 0 END) employee_provident_fund,
            MAX(CASE WHEN sd.salary_component = 'Employee State Insurance' THEN sd.amount ELSE 0 END) esic,
            MAX(CASE WHEN sd.salary_component = 'Labour Welfare Fund' THEN sd.amount ELSE 0 END) labour_welfare_fund,
            MAX(CASE WHEN sd.salary_component = 'Govt Labour Welfare Fund' THEN sd.amount ELSE 0 END) glwf,
            MAX(CASE WHEN sd.salary_component = 'Income Tax' THEN sd.amount ELSE 0 END) income_tax,
            SUM(
                CASE
                    WHEN sd.parentfield = 'deductions'
                     AND sd.salary_component IN ('National Pension System', 'National Pension Scheme - NPS')
                    THEN sd.amount
                    ELSE 0
                END
            ) nps,
            SUM(CASE WHEN sd.parentfield = 'deductions' AND sd.salary_component = 'Loan' THEN sd.amount ELSE 0 END) amount_to_deduct,
            SUM(CASE WHEN sd.parentfield = 'deductions' AND sd.salary_component = 'Loan' THEN sd.amount ELSE 0 END) deducted_amount,
            SUM(CASE WHEN sd.parentfield = 'deductions' AND sd.salary_component = 'Salary Advance' THEN sd.amount ELSE 0 END) salary_advance,
            MAX(CASE WHEN sd.salary_component = 'Other' THEN sd.amount ELSE 0 END) other_ded,
            ss.gross_pay as gross_pay_total_earned,
            ss.total_deduction,
            ss.rounded_total as net_payment,
            ss.gross_pay - MAX(CASE WHEN sd.salary_component = 'Incentives' THEN sd.amount ELSE 0 END) as gross_pay_actual
        FROM
            `tabSalary Slip` ss
        LEFT JOIN
            `tabEmployee` e ON e.name = ss.employee
        LEFT JOIN
            `tabSalary Structure Assignment` ssa
            ON ssa.name = (
                SELECT ssa2.name
                FROM `tabSalary Structure Assignment` ssa2
                WHERE ssa2.employee = ss.employee
                  AND ssa2.company = ss.company
                  AND ssa2.docstatus = 1
                  AND (COALESCE(ss.salary_structure, '') = '' OR ssa2.salary_structure = ss.salary_structure)
                  AND ssa2.from_date <= ss.end_date
                ORDER BY ssa2.from_date DESC, ssa2.creation DESC
                LIMIT 1
            )
        LEFT JOIN
            `tabSalary Structure` st
            ON st.name = COALESCE(ss.salary_structure, ssa.salary_structure)

        LEFT JOIN
            `tabSalary Detail` sd ON sd.parent = ss.name
        WHERE
            {where_sql}
            AND (ss.start_date BETWEEN %(from_date)s AND %(to_date)s
            AND ss.end_date BETWEEN %(from_date)s AND %(to_date)s)
        GROUP BY
            ss.name
        """,
        params,
        as_dict=True,
    )

    result = []
    for res in sql:
        # Fill defaults
        set_attendance_defaults(res)

        # ✅ Salary Structure allotted amounts in structure order
        apply_salary_structure_allotted(res)

        # ✅ New Form 14 integration
        apply_new_form_14(filters, res)

        # Tour / loan / holiday overlap / working days / tallies (your same logic)
        apply_tour_logic(res, from_date, to_date)
        apply_loan_installment_logic(res, from_date, to_date)
        apply_salary_slip_loan_deduction(res)
        apply_holiday_tour_overlap(res, from_date, to_date)

        res["working_days"] = (res.get("month_days") or 0) - (
            (res.get("weekly_off") or 0) + (res.get("holiday") or 0)
        )

        apply_report_date_format(res)
        apply_column_precision(res, precision_map)
        result.append(res)

    if filters.get("summarized_view"):
        return get_division_summary_data(result, columns)

    return add_division_summary_rows(result, columns)


def get_division_sort_key(row):
    return (
        normalize_division_name(row.get("division")).casefold(),
        get_employee_code_sort_key(row.get("emp")),
        (row.get("emp_name") or "").strip().casefold(),
    )


def get_employee_code_sort_key(employee_code):
    employee_code = str(employee_code or "").strip()
    if employee_code.isdigit():
        return (0, int(employee_code))
    return (1, employee_code.casefold())


def normalize_division_name(division_name):
    division_name = (division_name or "").strip()
    return division_name or "No Division"


def add_division_summary_rows(rows, columns):
    if not rows:
        return []

    rows = sorted(rows, key=get_division_sort_key)
    numeric_fields = get_numeric_fieldnames(columns)
    precision_map = get_column_precision_map(columns)
    grouped_rows = []
    grand_total_row = make_summary_row(
        columns, numeric_fields, "GRAND TOTAL", "grand_total"
    )
    current_division = None
    division_total_row = None

    # Insert division header and total rows after all employee-level calculations are ready.
    for row in rows:
        division_name = normalize_division_name(row.get("division"))
        row["row_type"] = "detail"

        if division_name != current_division:
            if division_total_row:
                apply_column_precision(division_total_row, precision_map)
                grouped_rows.append(division_total_row)

            grouped_rows.append(make_division_header_row(columns, division_name))
            division_total_row = make_summary_row(
                columns, numeric_fields, "TOTAL", "division_total"
            )
            current_division = division_name

        grouped_rows.append(row)
        accumulate_numeric_fields(division_total_row, row, numeric_fields)
        accumulate_numeric_fields(grand_total_row, row, numeric_fields)

    if division_total_row:
        apply_column_precision(division_total_row, precision_map)
        grouped_rows.append(division_total_row)

    apply_column_precision(grand_total_row, precision_map)
    grouped_rows.append(grand_total_row)
    return grouped_rows


def get_division_summary_data(rows, columns):
    if not rows:
        return []

    rows = sorted(rows, key=get_division_sort_key)
    precision_map = get_column_precision_map(columns)
    numeric_fields = [
        fieldname
        for fieldname in get_numeric_fieldnames(columns)
        if fieldname != "manpower"
    ]
    summary_rows = []
    grand_total_row = make_summary_row(
        columns,
        numeric_fields,
        "GRAND TOTAL",
        "grand_total",
        label_fieldname="division",
    )
    division_totals = {}
    division_employees = {}
    grand_total_employees = set()

    for row in rows:
        division_name = normalize_division_name(row.get("division"))
        division_total = division_totals.get(division_name)

        if not division_total:
            division_total = make_summary_row(
                columns,
                numeric_fields,
                division_name,
                "division_summary",
                label_fieldname="division",
            )
            division_totals[division_name] = division_total
            division_employees[division_name] = set()
            summary_rows.append(division_total)

        accumulate_numeric_fields(division_total, row, numeric_fields)
        accumulate_numeric_fields(grand_total_row, row, numeric_fields)

        employee = row.get("emp")
        if employee and employee not in division_employees[division_name]:
            division_employees[division_name].add(employee)
            division_total["manpower"] = (division_total.get("manpower") or 0) + 1

        if employee and employee not in grand_total_employees:
            grand_total_employees.add(employee)
            grand_total_row["manpower"] = (grand_total_row.get("manpower") or 0) + 1

    for row in summary_rows:
        apply_column_precision(row, precision_map)

    apply_column_precision(grand_total_row, precision_map)
    summary_rows.append(grand_total_row)
    return summary_rows


def get_numeric_fieldnames(columns):
    numeric_types = {"Currency", "Float", "Int", "Percent"}
    return [
        column.get("fieldname")
        for column in columns
        if column.get("fieldname") and column.get("fieldtype") in numeric_types
    ]


def get_column_precision_map(columns):
    precision_map = {}
    for column in columns:
        fieldname = column.get("fieldname")
        fieldtype = column.get("fieldtype")

        if not fieldname or fieldtype not in {"Currency", "Float", "Int", "Percent"}:
            continue

        if fieldtype == "Int":
            precision_map[fieldname] = 0
            continue

        precision_map[fieldname] = int(column.get("precision") or 0)

    return precision_map


def apply_column_precision(row, precision_map):
    for fieldname, precision in precision_map.items():
        value = row.get(fieldname)
        if value is None:
            continue
        row[fieldname] = flt(value, precision)

    return row


def make_empty_report_row(columns, row_type):
    row = {
        column.get("fieldname"): None for column in columns if column.get("fieldname")
    }
    row["row_type"] = row_type
    return row


def make_division_header_row(columns, division_name):
    row = make_empty_report_row(columns, "division_header")
    row["emp_name"] = division_name
    return row


def make_summary_row(
    columns, numeric_fields, label, row_type, label_fieldname="emp_name"
):
    row = make_empty_report_row(columns, row_type)
    row[label_fieldname] = label
    if row_type in {"division_total", "grand_total"}:
        set_xlsx_cell_style_like_header(row, label_fieldname)
    for fieldname in numeric_fields:
        row[fieldname] = 0
    return row


def accumulate_numeric_fields(total_row, source_row, numeric_fields):
    for fieldname in numeric_fields:
        total_row[fieldname] = flt(total_row.get(fieldname)) + flt(
            source_row.get(fieldname)
        )


def apply_report_date_format(row):
    for fieldname in ("date_of_birth", "date_of_joining"):
        row[fieldname] = format_report_date(row.get(fieldname))


def format_report_date(value):
    if not value:
        return value
    return getdate(value).strftime(REPORT_DATE_FORMAT)


# ---------------- Salary Structure helpers ----------------
def apply_salary_structure_allotted(res):
    # reset allotted fields
    res.update(
        {
            "earned_basic_alotted": 0,
            "conveyance_alotted": 0,
            "canteen_allowance_alotted": 0,
            "children_allowance_alotted": 0,
            "education_allowance_alotted": 0,
            "house_rent_allowance_alotted": 0,
            "special_pay_alotted": 0,
            "washing_allowance_alotted": 0,
            "over_time_alotted": 0,
            "incentive_alotted": 0,
            "transport_allowance_alotted": 0,
            "misc_alotted": 0,
        }
    )

    sst_name = res.get("sst_name")
    if not sst_name:
        res["gross_pay_alotted"] = flt(res.get("gross_pay_alotted"))
        return

    # pull Salary Detail for Salary Structure in the order they appear (idx)
    rows = frappe.db.sql(
        """
        SELECT salary_component, amount, parentfield
        FROM `tabSalary Detail`
        WHERE parenttype = 'Salary Structure'
          AND parent = %s
        ORDER BY idx
        """,
        (sst_name,),
        as_dict=True,
    )

    # map structure components to your fixed fields
    for r in rows:
        comp = (r.get("salary_component") or "").strip()
        amt = flt(r.get("amount") or 0)

        if comp == "Basic":
            res["earned_basic_alotted"] = amt
        elif comp == "Conveyance":
            res["conveyance_alotted"] = amt
        elif comp == "Canteen Allowance":
            res["canteen_allowance_alotted"] = amt
        elif comp in ("Children Allowance", "Children Hostel Allowance"):
            res["children_allowance_alotted"] = amt
        elif comp == "Education Allowance":
            res["education_allowance_alotted"] = amt
        elif comp == "House Rent Allowance":
            res["house_rent_allowance_alotted"] = amt
        elif comp in ("Special Pay", "Special Allowances"):
            res["special_pay_alotted"] = amt
        elif comp == "Washing Allowance":
            res["washing_allowance_alotted"] = amt
        elif comp == "Over Time":
            res["over_time_alotted"] = amt
        elif comp == "Incentives":
            res["incentive_alotted"] = amt
        elif comp in ("Transport Allowance", "Local Transport Allowance"):
            res["transport_allowance_alotted"] = amt
        elif comp in ("Miscellaneous", "MISC"):
            res["misc_alotted"] = amt

    total_earnings = sum(
        flt(r.get("amount")) for r in rows if r.get("parentfield") == "earnings"
    )
    res["gross"] = total_earnings
    res["gross_pay_alotted"] = flt(res.get("gross_pay_alotted")) or total_earnings


def get_salary_structure_components_in_order(sst_name):
    return [
        r["salary_component"]
        for r in frappe.db.sql(
            """
            SELECT salary_component
            FROM `tabSalary Detail`
            WHERE parenttype = 'Salary Structure'
              AND parent = %s
            ORDER BY idx
            """,
            (sst_name,),
            as_dict=True,
        )
        if r.get("salary_component")
    ]


def get_latest_effective_salary_structure(employee, slip_start_date):
    return (
        frappe.db.sql(
            """
        SELECT salary_structure
        FROM `tabSalary Structure Assignment`
        WHERE employee = %s
          AND docstatus = 1
          AND from_date <= %s
        ORDER BY from_date DESC
        LIMIT 1
        """,
            (employee, slip_start_date),
            as_dict=True,
        )[0].get("salary_structure")
        if employee
        else None
    )


# ---------------- Form 14 ----------------
def apply_new_form_14(filters, res):
    try:
        branch = filters.get("branch") or res.get("branch")
        cols_14, rows_14 = new_form_14.execute(
            {
                "company": filters.get("company"),
                "year": filters.get("year"),
                "month": filters.get("month"),
                "branch": branch,
                "division": filters.get("division"),
                "department": filters.get("department"),
                "employee": res.get("emp"),
                "processed_report": 1,
            }
        )
        if rows_14:
            d = rows_14[0]
            res["present_real"] = d.get("p", 0) or 0
            res["absent"] = d.get("a", 0) or 0
            res["earned_leave"] = d.get("el", 0) or 0
            res["casual_leave"] = d.get("cl", 0) or 0
            res["comp_off"] = d.get("co", 0) or 0
            res["od"] = d.get("od", 0) or 0
            res["weekly_off"] = d.get("wo", 0) or 0
            res["holiday"] = d.get("ho", 0) or 0  # new report uses ho
    except Exception:
        frappe.log_error(
            title="Detailed Salary Register - Form 14 Error",
            message=frappe.get_traceback(),
        )
        set_attendance_defaults(res)


# ---------------- Existing business logic (kept same style) ----------------
def set_attendance_defaults(res):
    res["present_real"] = 0
    res["absent"] = 0
    res["earned_leave"] = 0
    res["casual_leave"] = 0
    res["comp_off"] = 0
    res["od"] = 0
    res["weekly_off"] = 0
    res["holiday"] = 0
    res["tour_for_office"] = 0


def apply_tour_logic(res, from_date, to_date):
    res["tour_for_office"] = 0
    # educt_od = 0

    tour_sql = frappe.db.sql(
        """
        SELECT
            SUM(CASE WHEN att.half_day = 0 THEN 1 WHEN att.half_day = 1 THEN 0.5 ELSE 0 END) AS od,
            IFNULL(DATEDIFF(att.to_date, att.from_date) + 1, 0) as diff
        FROM
            `tabAttendance Request` att
        WHERE
            att.employee = %s
            AND (att.from_date BETWEEN %s AND %s AND att.to_date BETWEEN %s AND %s)
            AND att.docstatus = 1
            AND att.reason = 'Tour'
        """,
        (
            res["emp"],
            getdate(from_date),
            getdate(to_date),
            getdate(from_date),
            getdate(to_date),
        ),
        as_dict=True,
    )

    if tour_sql:
        diff = tour_sql[0].get("diff") or 0
        od_val = tour_sql[0].get("od") or 0

        if diff == 1:
            res["tour_for_office"] = od_val or 0
            res["od"] = (res.get("od") or 0) - (od_val or 0)

        if diff > 1:
            res["tour_for_office"] = diff
            res["od"] = (res.get("od") or 0) - diff


def apply_loan_installment_logic(res, from_date, to_date):
    installment_sql = frappe.db.sql(
        """
        SELECT
            ads.name additional_salary,
            ads.amount,
            ads.payroll_date,
            ads.ref_docname,
            ads.ref_doctype,
            ads.employee,
            ea.name,
            ea.advance_amount as sanctioned_amount
        FROM
            `tabEmployee Advance` ea
        LEFT JOIN
            `tabAdditional Salary` ads ON ads.ref_docname = ea.name
        WHERE
            ads.payroll_date BETWEEN %s AND %s
            AND ads.employee = %s
            AND ads.ref_doctype = 'Employee Advance'
        """,
        (from_date, to_date, res.get("emp")),
        as_dict=True,
    )

    opening_loan = 0
    if installment_sql:
        for i in installment_sql:
            opening_loan_sql = frappe.db.sql(
                """
                SELECT SUM(ads.amount) amount
                FROM `tabEmployee Advance` ea
                LEFT JOIN `tabAdditional Salary` ads ON ads.ref_docname = ea.name
                WHERE ads.payroll_date < %s
                  AND ads.employee = %s
                  AND ads.ref_doctype = %s
                """,
                (i.get("payroll_date"), i.get("employee"), i.get("ref_doctype")),
                as_dict=True,
            )
            paid_before = opening_loan_sql[0].get("amount") if opening_loan_sql else 0

            if paid_before:
                opening_loan = (i.get("sanctioned_amount") or 0) - paid_before
            else:
                opening_loan = opening_loan + (i.get("sanctioned_amount") or 0)

            res["loan_opening_balance"] = opening_loan

            closing_loan_sql = frappe.db.sql(
                """
                SELECT SUM(ads.amount) amount
                FROM `tabEmployee Advance` ea
                LEFT JOIN `tabAdditional Salary` ads ON ads.ref_docname = ea.name
                WHERE ads.payroll_date > %s
                  AND ads.employee = %s
                  AND ads.ref_doctype = %s
                """,
                (i.get("payroll_date"), i.get("employee"), i.get("ref_doctype")),
                as_dict=True,
            )
            res["loan_closing"] = (
                closing_loan_sql[0]["amount"]
                if closing_loan_sql and closing_loan_sql[0].get("amount")
                else 0
            )
    else:
        res["loan_opening_balance"] = 0
        res["loan_closing"] = 0


def apply_salary_slip_loan_deduction(res):
    sal_slip = frappe.get_doc("Salary Slip", res.get("salary_slip"))
    amt_to_deduct = 0
    salary_advance = 0
    for d in sal_slip.deductions:
        if d.get("salary_component") == "Loan":
            amt_to_deduct += flt(d.get("amount"))
        if d.get("salary_component") == "Salary Advance":
            salary_advance += flt(d.get("amount"))

    salary_slip_loan_payment = 0
    for loan in sal_slip.get("loans") or []:
        salary_slip_loan_payment += flt(loan.get("total_payment"))

    res["amount_to_deduct"] = amt_to_deduct
    res["deducted_amount"] = amt_to_deduct
    res["loan"] = amt_to_deduct + salary_slip_loan_payment
    res["total_deduction"] = flt(res.get("total_deduction")) + salary_slip_loan_payment
    res["salary_advance"] = salary_advance


def apply_holiday_tour_overlap(res, from_date, to_date):
    deduct_od = 0

    holiday_att = frappe.db.sql(
        """
        SELECT h.holiday_date, h.weekly_off
        FROM `tabHoliday List` hl
        LEFT JOIN `tabHoliday` h ON hl.name = h.parent
        WHERE hl.name = %s
          AND h.holiday_date BETWEEN %s AND %s
        """,
        (res.get("holiday_list"), getdate(from_date), getdate(to_date)),
        as_dict=True,
    )

    deduct_tour_list = frappe.db.get_list(
        "Attendance Request",
        {
            "docstatus": 1,
            "employee": res["emp"],
            "reason": "Tour",
            "from_date": ["between", [str(getdate(from_date)), str(getdate(to_date))]],
            "to_date": ["between", [str(getdate(from_date)), str(getdate(to_date))]],
        },
        ["name", "from_date", "to_date"],
    )

    if deduct_tour_list:
        for h in holiday_att:
            holiday_date = getdate(h["holiday_date"])
            for i in deduct_tour_list:
                if getdate(i["from_date"]) <= holiday_date <= getdate(i["to_date"]):
                    deduct_od += 1

        res["tour_for_office"] = (res.get("tour_for_office") or 0) - deduct_od
        res["od"] = (res.get("od") or 0) + deduct_od


# ---------------- Date utils ----------------
def month_to_mm(month):
    month_map = {
        "Jan": "01",
        "Feb": "02",
        "Mar": "03",
        "Apr": "04",
        "May": "05",
        "Jun": "06",
        "Jul": "07",
        "Aug": "08",
        "Sep": "09",
        "Oct": "10",
        "Nov": "11",
        "Dec": "12",
    }
    mm = month_map.get(month)
    if not mm:
        frappe.throw(f"Invalid month: {month}")
    return mm


def get_month_range(year, month):
    mm = month_to_mm(month)
    start = getdate(f"{year}-{mm}-01")
    end = get_last_day(start)
    return f"{start} 00:00:00", f"{end} 23:59:59"
