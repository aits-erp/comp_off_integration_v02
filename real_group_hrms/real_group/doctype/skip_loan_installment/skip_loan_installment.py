# Copyright (c) 2024, Step Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import add_to_date, get_first_day


class SkipLoanInstallment(Document):
	
	# def before_save(self):
	# 	if len(self.upcoming_installment) == 0:
	# 		frappe.throw("Kindly Select the installment to Skip!!")


	def on_submit(self):

		
		
		# if self.workflow_state == "Approved" and len(self.upcoming_installment) > 0:
		
		if self.workflow_state == "Approved":

			self_ins = frappe.get_doc("DocType", "Skip Loan Installment")
			for field in self_ins.fields:
				if field.fieldname == 'loan_installment':
					field.fieldtype = 'Data'
					field.options = ''
					break

			self_ins.save()
			frappe.db.commit()
			
			pending_ads = frappe.db.get_list("Skip Loan Installment", 
				filters = [
					["Skip Loan Installment","workflow_state","in",["Pending at HOD","Pending at HR"]],
					["Skip Loan Installment","active_loans","=",self.active_loans],
					["Skip Loan Installment","name","!=",self.name]
					],
				fields=['name'],
				)
			if len(pending_ads) > 0:
				self_ins = frappe.get_doc("DocType", "Skip Loan Installment")
				for field in self_ins.fields:
					if field.fieldname == 'loan_installment':
						field.fieldtype = 'Link'
						field.options = 'Additional Salary'
						break

				self_ins.save()
				frappe.db.commit()
				frappe.throw(f"Request is already under process for this ref No:{pending_ads[0].get('name')} \n Kindly Contact Your HR")
			else:
				all_adds = frappe.db.get_list("Additional Salary", 
					filters = [
							["Additional Salary","ref_docname","=",self.active_loans],
							["Additional Salary","ref_doctype","=","Employee Advance"],
							["Additional Salary","payroll_date",">", self.posting_date]
							], 
					fields=['name', 'payroll_date'],
					order_by = 'payroll_date desc',
					limit = 1)
				last_date = str(all_adds[0].get("payroll_date"))
				last_installment_date = last_date

				ads = frappe.get_doc("Additional Salary", self.loan_installment)
				ads.cancel()

				next_installment = get_first_day(add_to_date(last_installment_date, months = 1))

				additional_salary=frappe.get_doc(dict(
					amount = ads.amount,
					doctype = "Additional Salary",
					employee = self.employee,
					employee_name = self.employee_name,
					overwrite_salary_structure_amount = 0,
					ref_docname = self.active_loans,
					ref_doctype = "Employee Advance",
					salary_component = "Loan",
					payroll_date = next_installment,
					type = "Deduction",
					custom_skip_from_document = ads.name
					)
				)
				additional_salary.save()
				additional_salary.submit()

				self_ins = frappe.get_doc("DocType", "Skip Loan Installment")
				for field in self_ins.fields:
					if field.fieldname == 'loan_installment':
						field.fieldtype = 'Link'
						field.options = 'Additional Salary'
						break

				self_ins.save()
				frappe.db.commit()




@frappe.whitelist()
def get_additional_salary(employee,ref_doctype,ref_docname,posting_date):
	result = frappe.db.sql(f"""
		SELECT 
			name,
			amount,
			payroll_date,
			type,
			salary_component
		FROM
			`tabAdditional Salary`
		WHERE
			docstatus = 1
			AND employee = %s
			AND ref_doctype = %s
			AND ref_docname = %s
			AND payroll_date >= %s
		ORDER BY
			payroll_date ASC
	""",(employee, ref_doctype, ref_docname, posting_date), as_dict=1)

	return result


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_employee_advance(doctype, txt, searchfield, start, page_len, filters):
	employee = filters.get("employee")
	values = {"employee": employee, "txt":txt}

	return frappe.db.sql("""
		SELECT name
		FROM `tabEmployee Advance`
		WHERE docstatus = 1
			AND employee = %(employee)s
			AND return_amount != paid_amount
	""", values=values, as_dict = 0)