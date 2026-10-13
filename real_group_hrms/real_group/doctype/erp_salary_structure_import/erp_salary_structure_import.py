# Copyright (c) 2024, Step Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from real_group_hrms.real_group.integration import config_master , employee_rate_master


class ERPSalaryStructureImport(Document):
	
	def before_submit(self):


		company = self.company
		emp_catg = self.employee_category

		earning_and_deductions = config_master(company=company, emp_catg=emp_catg)
		frappe.log_error("abcd", earning_and_deductions)
		# all_employee = frappe.db.get_all("Employee", {"company": company, "custom_emp_category": emp_catg, "status": "Active"})
		# all_employee = [{'name': '50003'}]

		# erp_ss_emp = frappe.get_doc("ERP Salary Structure Import", self.name)
		
		for employee in self.details:
			emp_code = employee.employee

			componant_rates = employee_rate_master(emp_code, company)
			frappe.log_error("componant_rate", componant_rates)
		
			salary_structure = frappe.get_doc(dict(
					__newname = emp_code,
					company = company,
					doctype = "Salary Structure",
					is_active = "Yes",
					letter_head = company,
					owner = frappe.db.get_value("User" , frappe.session.user , ("username")),
					payroll_frequency = "Monthly",
					custom_reference_no = self.name
				))
			total_earnings = 0.0
			total_deductions = 0.0
			basic_pay = 0.0
			for rec in earning_and_deductions:
				if "D" in rec.get("AFNO") :
					amount = 0.0
					for rate in componant_rates:
						if rate.get("AFNO") == rec.get("AFNO"):
							depends_on_formula = frappe.db.count("Salary Component", {"custom_erp_code": rate.get("AFCODE"), "amount_based_on_formula": 1})
							if depends_on_formula == 0:
								amount = rate.get("AFRATE")

					salary_structure.append("deductions", dict(
							abbr = rec.get("abbr"),
							custom_erp_rate = rec.get("AFRATE"),
							salary_component = rec.get("salary_component"),
							amount = amount
						))

					total_deductions = total_deductions + amount

				else:
					amount = 0.0
					for rate in componant_rates:
						if rate.get("AFNO") == rec.get("AFNO"):
							depends_on_formula = frappe.db.count("Salary Component", {"custom_erp_code": rate.get("AFCODE"), "amount_based_on_formula": 1})
							if depends_on_formula == 0:
								amount = rate.get("AFRATE")
						
					if rec.get("abbr") == "B":
						basic_pay = amount


					salary_structure.append("earnings", dict(
							abbr = rec.get("abbr"),
							custom_erp_rate = rec.get("AFRATE"),
							salary_component = rec.get("salary_component"),
							amount = amount
						))
					total_earnings = total_earnings + amount

			salary_structure.total_earning = total_earnings
			salary_structure.total_deduction = total_deductions

			try:
				salary_structure.insert()
				if self.submit_entries == 1:
					salary_structure.submit()
			except Exception as e:
				frappe.throw(f"Error While Importing Salary Structure for Employee - {emp_code} \n {str(e)}")


			# frappe.throw(str(basic_pay))
			emp = frappe.get_doc("Employee", emp_code)
			ss_assign = frappe.get_doc(dict(
				base = total_earnings,
				company = emp.company,
				department = emp.department,
				designation = emp.designation,
				doctype = "Salary Structure Assignment",
				employee = emp_code,
				employee_name = emp.employee_name,
				from_date = self.assignment_date,
				grade = emp.grade,
				salary_structure = salary_structure.name,
				custom_reference_no = self.name,
				custom_basic_pay = basic_pay,
				income_tax_slab = employee.income_tax_slab
			))

			try:
				ss_assign.insert()
				if self.submit_entries == 1:
					ss_assign.submit()
			except Exception as e:
				frappe.throw(f"Error While Importing Salary Structure Assignment for Employee - {emp_code} \n {str(e)}")


			employee.salary_structure = salary_structure.name
