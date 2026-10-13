import frappe


def execute():
    Company = frappe.qb.DocType("Company")
    query = frappe.qb.from_(Company).select("*")
    companies = query.run(as_dict=True)

    for company in companies:
        series_exists = frappe.db.exists("Employee Series", {"company": company.name, "is_active": 1})
        if series_exists:
            continue

        doc = frappe.get_doc(
            {
                "doctype": "Employee Series",
                "company": company.name,
                "is_active": 1,
                "start": company.custom_employee_code_starting_from,
                "end": company.custom_employee_code_ending_at,
            }
        )
        doc.insert(ignore_if_duplicate=True)
