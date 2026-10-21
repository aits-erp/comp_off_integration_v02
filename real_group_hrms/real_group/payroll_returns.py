import frappe
import json

@frappe.whitelist()
def generate_epf_txt():

    company = frappe.form_dict.get("company")
    branch = frappe.form_dict.get("branch")
    division = frappe.form_dict.get("division")
    department = frappe.form_dict.get("department")
    employee = frappe.form_dict.get("employee")
    month = frappe.form_dict.get("month")
    year = frappe.form_dict.get("year")

    company = company.replace("+", " ") if company else ''
    branch = branch.replace("+", " ") if branch else ''
    division = division.replace("+", " ") if division else ''
    department = department.replace("+", " ") if department else ''
    employee = employee.replace("+", " ") if employee else ''
    month = frappe.form_dict.get("month")
    year = frappe.form_dict.get("year")

    data = frappe.call(   
		"frappe.desk.query_report.run",
		report_name="EPF ECR",
		filters={
            "company" : company,
            "branch" : branch,
            "division" : division,
            "department" : department,
            "employee" : employee,
            "month" : month,
            "year" : year,
		},
		ignore_prepared_report=True
		)

    data = data["result"]
 
    if len(data) == 0:
        frappe.throw("No Records Found")

    content = ""
    for d in data:
        content = f'{content}{d.get("uan")}#~#{d.get("member_name")}#~#{d.get("gross_wages"):.0f}#~#{d.get("epf_wages"):.0f}#~#{d.get("eps_wages"):.0f}#~#{d.get("edli_wages"):.0f}#~#{d.get("epf_cont"):.0f}#~#{d.get("eps_cont"):.0f}#~#{d.get("epf_eps_diff"):.0f}#~#{d.get("refund"):.0f}\n'
    frappe.response["filename"] = f"EPF_ECR_{data[0].get('month')}-{data[0].get('year')}.txt"
    frappe.response["filecontent"] = content
    frappe.response["type"] = "download"
