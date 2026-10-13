import frappe
from frappe.utils import ceil, floor, flt, getdate, rounded
from hrms.payroll.utils import sanitize_expression

ESIC_SALARY_COMPONENT = "Employee State Insurance"
ESIC_ABBR = "SI"
HIDDEN_PRINT_EARNING_COMPONENTS = {
    "incentive",
    "incentives",
    "over time",
    "arrear",
}
HIDDEN_PRINT_DEDUCTION_COMPONENTS = {
    "salary advance",
    "other",
    "miscellaneous",
    "pf arrear",
    "esi arrear",
}


def before_save(doc, method=None):
    values = get_salary_structure_assignment_values(doc.salary_structure)
    doc.custom_basic_pay = values.get("basic_pay")
    doc.base = values.get("base")
    set_esic_exit_date(doc)
    validate_workflow_state(doc)


def validate_workflow_state(doc):
    if doc.workflow_state == "Rejected" and not (doc.custom_reject_reason or "").strip():
        frappe.throw(frappe._("Kindly set the reason for rejection"))


@frappe.whitelist()
def get_salary_structure_assignment_values(salary_structure):
    return {
        "basic_pay": get_salary_structure_basic_pay(salary_structure),
        "base": get_salary_structure_total_earning(salary_structure),
    }


@frappe.whitelist()
def get_salary_structure_basic_pay(salary_structure):
    if not salary_structure:
        return 0

    basic_pay = frappe.db.get_value(
        "Salary Detail",
        filters={
            "parent": salary_structure,
            "parenttype": "Salary Structure",
            "parentfield": "earnings",
            "salary_component": "Basic",
            "abbr": "B",
        },
        fieldname="amount",
        order_by="idx asc",
    )

    return flt(basic_pay)


def get_salary_structure_total_earning(salary_structure):
    if not salary_structure:
        return 0

    return flt(frappe.db.get_value("Salary Structure", salary_structure, "total_earning"))


@frappe.whitelist()
def round_payroll_amount(value):
    return int(rounded(flt(value)))


def clean_payroll_amount(value):
    value = flt(value)
    return int(value) if value == int(value) else value


@frappe.whitelist()
def get_projected_breakup(salary_structure_assignment):
    if not salary_structure_assignment:
        return _empty_projected_breakup()

    doc = frappe.get_doc("Salary Structure Assignment", salary_structure_assignment)
    if not doc.salary_structure:
        return _empty_projected_breakup()

    salary_structure = frappe.get_doc("Salary Structure", doc.salary_structure)
    employee = frappe.get_cached_doc("Employee", doc.employee).as_dict() if doc.employee else {}
    data = _get_formula_context(doc, salary_structure, employee)

    earnings = _get_projected_rows(salary_structure.earnings, data)
    deductions = _get_projected_rows(salary_structure.deductions, data)

    pf_employer_contribution = _get_pf_employer_contribution(earnings, deductions)
    esic_employer_contribution = _get_esic_employer_contribution(earnings, deductions)
    bonus_exgratia = _get_bonus_exgratia(doc, employee, earnings)
    print_earnings = _get_print_rows(earnings, HIDDEN_PRINT_EARNING_COMPONENTS)
    print_deductions = _get_print_rows(deductions, HIDDEN_PRINT_DEDUCTION_COMPONENTS)
    total_earnings = clean_payroll_amount(sum(row.amount or 0 for row in print_earnings))
    total_deductions = clean_payroll_amount(sum(row.amount or 0 for row in print_deductions))

    return {
        "earnings": print_earnings,
        "deductions": print_deductions,
        "total_earnings": total_earnings,
        "total_earnings_yearly": clean_payroll_amount(total_earnings * 12),
        "total_deductions": total_deductions,
        "total_deductions_yearly": clean_payroll_amount(total_deductions * 12),
        "net_payable": clean_payroll_amount(total_earnings - total_deductions),
        "net_payable_yearly": clean_payroll_amount((total_earnings - total_deductions) * 12),
        "pf_employer_contribution": pf_employer_contribution,
        "pf_employer_contribution_yearly": pf_employer_contribution * 12,
        "esic_employer_contribution": esic_employer_contribution,
        "esic_employer_contribution_yearly": esic_employer_contribution * 12,
        "bonus_exgratia": bonus_exgratia,
        "bonus_exgratia_yearly": bonus_exgratia * 12,
    }


def _get_print_rows(rows, hidden_components):
    return [row for row in rows if (row.salary_component or "").strip().lower() not in hidden_components]


def _empty_projected_breakup():
    return {
        "earnings": [],
        "deductions": [],
        "total_earnings": 0,
        "total_earnings_yearly": 0,
        "total_deductions": 0,
        "total_deductions_yearly": 0,
        "net_payable": 0,
        "net_payable_yearly": 0,
        "pf_employer_contribution": 0,
        "pf_employer_contribution_yearly": 0,
        "esic_employer_contribution": 0,
        "esic_employer_contribution_yearly": 0,
        "bonus_exgratia": 0,
        "bonus_exgratia_yearly": 0,
    }


def _get_pf_employer_contribution(earnings, deductions):
    employee_pf = _get_component_amount(deductions, salary_component="Provident Fund", abbr="PF")
    basic = _get_component_amount(earnings, salary_component="Basic", abbr="B")

    if employee_pf <= 0 or basic <= 0:
        return 0

    pf_basic_limit = flt(frappe.db.get_single_value("Real Group Settings", "pf_basic_limit"))
    is_full_basic_pf = pf_basic_limit and basic > pf_basic_limit and round(employee_pf) == round(basic * 0.12)
    pf_base = basic if is_full_basic_pf else min(basic, pf_basic_limit) if pf_basic_limit else basic

    return round_payroll_amount(pf_base * 0.13)


def _get_esic_employer_contribution(earnings, deductions):
    employee_esic = _get_component_amount(deductions, salary_component=ESIC_SALARY_COMPONENT, abbr=ESIC_ABBR)
    basic = _get_component_amount(earnings, salary_component="Basic", abbr="B")

    if employee_esic <= 0 or basic <= 0:
        return 0

    esic_deduction_limit = flt(frappe.db.get_single_value("Real Group Settings", "esic_deduction_limit"))
    esic_base = min(basic, esic_deduction_limit) if esic_deduction_limit else basic

    return round_payroll_amount(esic_base * 0.0325)


def _get_bonus_exgratia(doc, employee, earnings):
    grade = doc.get("grade") or (employee or {}).get("grade")
    basic = _get_component_amount(earnings, salary_component="Basic", abbr="B")

    if not grade or basic <= 0:
        return 0

    is_bonus_applicable, bonus_percentage = frappe.db.get_value(
        "Employee Grade",
        grade,
        ["custom_is_bonus_applicable", "custom_bonus_percentage"],
    ) or (0, 0)

    if not is_bonus_applicable:
        return 0

    return round_payroll_amount(basic * flt(bonus_percentage) / 100)


def _get_component_amount(rows, salary_component=None, abbr=None):
    for row in rows:
        if (salary_component and row.salary_component == salary_component) or (abbr and row.abbr == abbr):
            return flt(row.amount)

    return 0


def set_esic_exit_date(doc):
    doc.custom_esi_exit_date = get_esic_exit_date_for_assignment(doc) or ""


def get_esic_exit_date_for_assignment(doc):
    if not doc.employee or not doc.salary_structure or not doc.from_date:
        return None

    current_esic = get_assignment_esic_amount(doc, ignore_exit_date=True)
    if current_esic > 0:
        return None

    period_start, period_end = get_esic_period(doc.from_date)
    from_date = getdate(doc.from_date)

    previous_assignment = get_previous_submitted_assignment(doc)
    if not previous_assignment:
        return None

    previous_exit_date = previous_assignment.get("custom_esi_exit_date")
    if previous_exit_date:
        previous_exit_date = getdate(previous_exit_date)
        if period_start <= previous_exit_date <= period_end and from_date <= previous_exit_date:
            return period_end

    previous_esic = get_assignment_esic_amount(previous_assignment, ignore_exit_date=True)
    if previous_esic > 0:
        return period_end

    return None


def get_previous_submitted_assignment(doc):
    filters = [
        ["Salary Structure Assignment", "employee", "=", doc.employee],
        ["Salary Structure Assignment", "docstatus", "=", 1],
        ["Salary Structure Assignment", "from_date", "<", doc.from_date],
    ]

    if doc.name:
        filters.append(["Salary Structure Assignment", "name", "!=", doc.name])

    previous_assignments = frappe.db.get_all(
        "Salary Structure Assignment",
        filters=filters,
        fields=[
            "name",
            "employee",
            "salary_structure",
            "from_date",
            "custom_basic_pay",
            "base",
            "custom_esi_exit_date",
        ],
        order_by="from_date desc, creation desc",
        limit=1,
    )

    return previous_assignments[0] if previous_assignments else None


def get_esic_period(date):
    date = getdate(date)

    if 4 <= date.month <= 9:
        return getdate(f"{date.year}-04-01"), getdate(f"{date.year}-09-30")

    if date.month >= 10:
        return getdate(f"{date.year}-10-01"), getdate(f"{date.year + 1}-03-31")

    return getdate(f"{date.year - 1}-10-01"), getdate(f"{date.year}-03-31")


def get_assignment_esic_amount(doc, ignore_exit_date=False):
    if not doc or not doc.get("salary_structure"):
        return 0

    as_dict = getattr(doc, "as_dict", None)
    if not callable(as_dict) and doc.get("name"):
        doc = frappe.get_doc("Salary Structure Assignment", doc.get("name"))

    salary_structure = frappe.get_doc("Salary Structure", doc.get("salary_structure"))
    employee = frappe.get_cached_doc("Employee", doc.get("employee")).as_dict() if doc.get("employee") else {}
    data = _get_formula_context(
        doc,
        salary_structure,
        employee,
        ignore_exit_date=ignore_exit_date,
    )

    _get_projected_rows(salary_structure.earnings, data)
    deductions = _get_projected_rows(salary_structure.deductions, data)

    return _get_component_amount(
        deductions,
        salary_component=ESIC_SALARY_COMPONENT,
        abbr=ESIC_ABBR,
    )


def _get_formula_context(doc, salary_structure, employee, ignore_exit_date=False):
    data = frappe._dict()
    as_dict = getattr(doc, "as_dict", None)
    data.update(as_dict() if callable(as_dict) else doc)
    data.update(employee or {})

    data.start_date = data.get("from_date")
    data.end_date = (
        data.get("from_date") if ignore_exit_date else data.get("custom_esi_exit_date") or data.get("from_date")
    )
    data.setdefault("custom_previous_base", 0)
    data.setdefault("custom_esi_exit_date", None)
    data.setdefault("payment_days", 1)
    data.setdefault("total_working_days", 1)
    data.setdefault("leave_without_pay", 0)
    data.setdefault("absent_days", 0)

    for abbr in frappe.get_all("Salary Component", pluck="salary_component_abbr"):
        data.setdefault(abbr, 0)

    # Direct component amounts are available before formulas are evaluated.
    for table in (salary_structure.earnings, salary_structure.deductions):
        for row in table:
            if row.abbr and not row.amount_based_on_formula:
                data[row.abbr] = flt(row.amount)

    return data


def _get_projected_rows(rows, data):
    projected_rows = []

    for row in rows:
        amount = _evaluate_salary_detail(row, data)
        if row.abbr:
            data[row.abbr] = amount

        projected_rows.append(
            frappe._dict(
                {
                    "salary_component": row.salary_component,
                    "abbr": row.abbr,
                    "amount": amount,
                    "yearly_amount": amount * 12,
                    "amount_based_on_formula": row.amount_based_on_formula,
                    "formula": row.formula,
                    "condition": row.condition,
                }
            )
        )

    return projected_rows


def _evaluate_salary_detail(row, data):
    if not _condition_matches(row, data):
        return 0

    amount = row.amount
    if row.amount_based_on_formula:
        formula = sanitize_expression(row.formula)
        if not formula:
            return 0

        amount = frappe.safe_eval(formula, _get_formula_globals(), data)

    amount = flt(amount, row.precision("amount"))
    if amount == 0:
        return 0

    if frappe.db.get_value("Salary Component", row.salary_component, "round_to_the_nearest_integer", cache=True):
        return round_payroll_amount(amount)

    return clean_payroll_amount(amount)


def _condition_matches(row, data):
    condition = sanitize_expression(row.condition)
    if not condition:
        return True

    return bool(frappe.safe_eval(condition, _get_formula_globals(), data))


def _get_formula_globals():
    return {
        "__builtins__": {},
        "int": int,
        "float": float,
        "round": round,
        "ceil": ceil,
        "floor": floor,
        "getdate": getdate,
    }
