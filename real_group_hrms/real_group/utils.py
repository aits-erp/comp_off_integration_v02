import frappe
import pyqrcode
from frappe.utils import flt, getdate, today


def get_qr_code(value, scale):
    qr = pyqrcode.create(value).png_as_base64_str(scale=scale, quiet_zone=1)
    return f'<img src="data:image/png;base64,{qr}" class="qrcode">'


@frappe.whitelist()
def get_salary_contributions(employee: str, salary_structure: str):
    """
    Returns PF and ESIC contributions (Employee + Employer side).
    Dynamically evaluates PF formula from Salary Detail (no hardcoding).
    """

    result = {
        "pf_employee_monthly": 0,
        "pf_employee_yearly": 0,
        "esic_employee_monthly": 0,
        "esic_employee_yearly": 0,
        "pf_employer_monthly": 0,
        "pf_employer_yearly": 0,
        "esic_employer_monthly": 0,
        "esic_employer_yearly": 0,
    }

    if not employee or not salary_structure:
        return result

    emp = frappe.get_doc("Employee", employee)
    ss = frappe.get_doc("Salary Structure", salary_structure)

    # --- Get Basic ---
    basic_row = next((e for e in ss.earnings if e.salary_component == "Basic"), None)
    basic_amount = flt(basic_row.amount) if basic_row else 0

    # --- Fetch PF formula from Salary Detail ---
    pf_row = frappe.db.get_value(
        "Salary Detail",
        {"parent": salary_structure, "salary_component": "Provident Fund"},
        ["formula"],
        as_dict=True,
    )

    pf_formula = (pf_row["formula"] or "").strip() if pf_row else ""

    pf_employee = pf_employer = 0

    if emp.custom_pf_number or emp.provident_fund_account:
        if pf_formula:
            try:
                # Debug log to confirm formula text and value
                frappe.logger().info(f"Evaluating PF formula for {salary_structure}: {pf_formula}, B={basic_amount}")

                # Prepare environment for safe evaluation
                local_vars = {"B": basic_amount}

                # Evaluate formula safely (e.g. ((B * 12) / 100) if B <= 15000 else 1800)
                pf_value = eval(pf_formula, {"__builtins__": {}}, local_vars)

                # If eval works and returns number
                if pf_value is not None:
                    pf_employee = round(flt(pf_value))
                    pf_employer = round(flt(pf_value))
                else:
                    # Fallback if eval returns None
                    pf_employee = round(basic_amount * 0.12)
                    pf_employer = round(basic_amount * 0.12)

            except Exception as e:
                frappe.log_error(
                    f"PF formula evaluation failed for {salary_structure}\nFormula: {pf_formula}\nError: {e}",
                    "PF Formula Error",
                )
                pf_employee = round(basic_amount * 0.12)
                pf_employer = round(basic_amount * 0.12)
        else:
            # No formula defined
            pf_employee = round(basic_amount * 0.12)
            pf_employer = round(basic_amount * 0.12)

    # --- ESIC logic ---
    gross_monthly = flt(ss.total_earning)
    esic_employee = esic_employer = 0

    if gross_monthly <= 21000:
        esic_employee = round(gross_monthly * 0.0075)
        esic_employer = round(gross_monthly * 0.0325)
    elif (
        getattr(emp, "custom_previous_base", 0) <= 21000
        and getattr(emp, "custom_esi_exit_date", None)
        and getdate(today()) <= getdate(emp.custom_esi_exit_date)
    ):
        esic_employee = round(gross_monthly * 0.0075)
        esic_employer = round(gross_monthly * 0.0325)

    # --- Return combined data ---
    result.update(
        {
            "pf_employee_monthly": pf_employee,
            "pf_employee_yearly": pf_employee * 12,
            "esic_employee_monthly": esic_employee,
            "esic_employee_yearly": esic_employee * 12,
            "pf_employer_monthly": pf_employer,
            "pf_employer_yearly": pf_employer * 12,
            "esic_employer_monthly": esic_employer,
            "esic_employer_yearly": esic_employer * 12,
        }
    )

    return result
