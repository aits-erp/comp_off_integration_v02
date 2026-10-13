import frappe
import json
from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip as ss

def process_arrear(self, *args, **kwargs):

	# pass

	ssa_list = frappe.db.get_all(
		"Salary Structure Assignment", 
		filters={"employee": self.employee, "docstatus": 1}, 
		order_by="creation DESC"
	)
	
	if len(ssa_list) > 0:
		ssa_doc = frappe.get_doc("Salary Structure Assignment", ssa_list[0].name)
		factor = self.base/ssa_doc.base
		from_date = ""
		if self.custom_arrears_from: # frappe.utils.get_first_day(self.custom_arrears_from):
			from_date = frappe.utils.get_first_day(self.custom_arrears_from)
		else:
			from_date = ssa_doc.creation

		sal_slip_list = frappe.db.sql(f"""
			SELECT
				name
			FROM
				`tabSalary Slip` ss
			WHERE 
				ss.start_date BETWEEN '{from_date}' AND '{frappe.utils.add_to_date(self.creation, days=-1)}'
				AND ss.end_date BETWEEN '{from_date}' AND '{frappe.utils.add_to_date(self.creation, days=-1)}'
				AND ss.employee = '{self.employee}'
				AND docstatus = 1
		""", as_dict=True)
		# sal_slip_list = frappe.db.get_all(
		# 	"Salary Slip", 
		# 	filters={
		# 		"employee": self.employee,
		# 		"creation": ["between", [from_date, frappe.utils.add_to_date(self.creation, days=-1)]],
		# 		"docstatus": 1
		# 	}
		# )
		total_arrears = 0
		total_earning = 0
		total_deduction = 0
		my_list = []
		earned = {}
		deducted = {}
		for slip in sal_slip_list:
			sal_slip_doc = frappe.get_doc("Salary Slip", slip.name)
			for earning in sal_slip_doc.earnings:
				total_earning += earning.amount
				earning.custom_revised_amount = factor * earning.amount
				frappe.db.set_value("Salary Detail", earning.name, 'custom_revised_amount',  factor*earning.amount)
				frappe.db.set_value("Salary Detail", earning.name, 'custom_arrears_difference',  (factor*earning.amount) - earning.amount)
				if earning.salary_component not in earned:
					earned[earning.salary_component] = factor*earning.amount - earning.amount
				elif earning.salary_component in earned:
					earned[earning.salary_component] += factor*earning.amount - earning.amount
			for deduction in sal_slip_doc.deductions:
				total_deduction += deduction.amount
				deduction.custom_revised_amount = factor * deduction.amount
				frappe.db.set_value("Salary Detail", deduction.name, 'custom_revised_amount',  factor*deduction.amount)
				frappe.db.set_value("Salary Detail", deduction.name, 'custom_arrears_difference',  (factor*deduction.amount) - deduction.amount)
				if deduction.salary_component not in deducted:
					deducted[deduction.salary_component] = factor*deduction.amount - deduction.amount
				if deduction.salary_component in deducted:
					deducted[deduction.salary_component] += factor*deduction.amount - deduction.amount

			sal_slip_doc.custom_gross_arrears = sal_slip_doc.gross_pay * factor
			sal_slip_doc.custom_total_deduction_arrears = sal_slip_doc.total_deduction * factor	
			sal_slip_doc.custom_net_pay_arrears = sal_slip_doc.net_pay * factor
			total_arrears += sal_slip_doc.net_pay * factor - sal_slip_doc.net_pay	
	
			sal_slip_doc.save()
		
		# arrear_doc = frappe.new_doc("Additional Salary")
		# arrear_doc.update(
		# 	{
		# 		"doctype": "Additional Salary",
		# 		"employee": self.employee,
		# 		"payroll_date": self.from_date,
		# 		"salary_component": "Arrear",
		# 		"amount": total_arrears,

		# 	}
		# ).save()
		# arrear_doc.submit()
		arr_slip_exists = frappe.db.get_list("Arrear Slip", filters={"salary_structure_assignment": self.name})
		if len(arr_slip_exists) == 0:
			arr_slip = frappe.get_doc(dict( 
				salary_structure_assignment = self.name,
				owner = self.owner, 
				creation = self.creation, 
				modified = self.modified, 
				modified_by = self.modified_by,  
				idx = self.idx,  
				employee = self.employee,  
				posting_date = self.from_date,  
				company = self.company, 
				payroll_frequency = "Monthly", 
				start_date = frappe.utils.get_first_day(self.from_date), 
				end_date = frappe.utils.get_last_day(self.from_date), 
				salary_structure = self.salary_structure, 
				doctype = "Arrear Slip",
				gross_pay = total_earning, 
				# base_gross_pay = self.base_gross_pay, 
				# gross_year_to_date = self.gross_year_to_date, 
				# base_gross_year_to_date = self.base_gross_year_to_date, 
				# custom_gross_arrears = self.custom_gross_arrears, 
				total_deduction = total_deduction, 
				# base_total_deduction = self.base_total_deduction, 
				# custom_bonus_rate = self.custom_bonus_rate, 
				# custom_bonus_amount = self.custom_bonus_amount, 
				# custom_total_deduction_arrears = self.custom_total_deduction_arrears, 
				net_pay = total_earning - total_deduction, 
				# base_net_pay = self.base_net_pay, 
				# rounded_total = self.rounded_total, 
				# base_rounded_total = self.base_rounded_total, 
				# custom_net_pay_arrears = self.custom_net_pay_arrears, 
				# year_to_date = self.year_to_date, 
				# base_year_to_date = self.base_year_to_date, 
				# month_to_date = self.month_to_date, 
				# base_month_to_date = self.base_month_to_date, 
				# total_in_words = self.total_in_words, 
				# base_total_in_words = self.base_total_in_words, 
				# ctc = self.ctc, 
				# income_from_other_sources = self.income_from_other_sources, 
				# total_earnings = self.total_earnings, 
				# non_taxable_earnings = self.non_taxable_earnings, 
				# standard_tax_exemption_amount = self.standard_tax_exemption_amount, 
				# tax_exemption_declaration = self.tax_exemption_declaration, 
				# deductions_before_tax_calculation = self.deductions_before_tax_calculation, 
				# annual_taxable_amount = self.annual_taxable_amount, 
				# income_tax_deducted_till_date = self.income_tax_deducted_till_date, 
				# current_month_income_tax = self.current_month_income_tax, 
				# future_income_tax_deductions = self.future_income_tax_deductions, 
				# total_income_tax = self.total_income_tax, 
				# bank_name = self.bank_name, 
				# bank_account_no = self.bank_account_no, 
				# doctype = "Arrear Slip", 
				# timesheets = self.timesheets, 
				# leave_details = self.leave_details,
				# earnings = self.earnings,
				# deductions = self.deductions
			))

			for e in earned:
				arr_slip.append("earnings", {
					"salary_component": e,
					"amount": earned[e],
					"parent": arr_slip.name,
					"doctype": "Arrear Detail"
				})
			for e in deducted:
				arr_slip.append("deductions", {
					"salary_component": e,
					"amount": deducted[e],
					"parent": arr_slip.name,
					"doctype": "Arrear Detail"
				})		
			arr_slip.insert()
			
def arrears_in_current_sal_slip(self, *args, **kwargs):
	all_sal_slip = frappe.db.get_all("Salary Slip", filters={"employee": self.employee, "custom_gross_arrears": [">", 0], "docstatus": ["=", "1"], "creation": ["<", frappe.utils.today()]})
	earned = {}
	deducted = {}
	total_earned = 0
	total_deducted = 0
	final_gross = 0
	final_deduction = 0

	for ss in all_sal_slip:
		sal_slip_doc = frappe.get_doc("Salary Slip", ss.name)
		for e in sal_slip_doc.earnings:
			if e.salary_component not in earned:
				earned[e.salary_component] = e.custom_arrears_difference
			elif e.salary_component in earned:
				earned[e.salary_component] = earned[e.salary_component] + e.custom_arrears_difference
			total_earned += e.custom_arrears_difference
		for e in sal_slip_doc.deductions:
			if e.salary_component not in deducted:
				deducted[e.salary_component] = e.custom_arrears_difference
			elif e.salary_component in deducted:
				deducted[e.salary_component] = deducted[e.salary_component] + e.custom_arrears_difference
			total_deducted += e.custom_arrears_difference

	net = total_earned - total_deducted
	if net == 0:
		net = 1
	arrear = 0
	for e in self.earnings:
		if e.salary_component == 'Arrear':
			arrear = e.amount
	
	k = arrear/net
	
	
	# arr_slip.submit()

	arr_slip = frappe.get_doc(dict( 
		owner = self.owner, 
		creation = self.creation, 
		modified = self.modified, 
		modified_by = self.modified_by, 
		docstatus = self.docstatus, 
		idx = self.idx, 
		custom_include_arrears = self.custom_include_arrears, 
		employee = self.employee, 
		employee_name = self.employee_name, 
		department = self.department, 
		designation = self.designation, 
		branch = self.branch, 
		custom_grade = self.custom_grade, 
		posting_date = self.posting_date, 
		letter_head = self.letter_head, 
		custom_division = self.custom_division, 
		custom_employee_category = self.custom_employee_category, 
		status = self.status, 
		company = self.company, 
		currency = self.currency, 
		exchange_rate = self.exchange_rate, 
		custom_payroll_series = self.custom_payroll_series, 
		payroll_frequency = self.payroll_frequency, 
		start_date = self.start_date, 
		end_date = self.end_date, 
		salary_structure = self.salary_structure, 
		mode_of_payment = self.mode_of_payment, 
		salary_slip_based_on_timesheet = self.salary_slip_based_on_timesheet, 
		deduct_tax_for_unclaimed_employee_benefits = self.deduct_tax_for_unclaimed_employee_benefits, 
		deduct_tax_for_unsubmitted_tax_exemption_proof = self.deduct_tax_for_unsubmitted_tax_exemption_proof, 
		total_working_days = self.total_working_days, 
		unmarked_days = self.unmarked_days, 
		leave_without_pay = self.leave_without_pay, 
		absent_days = self.absent_days, 
		payment_days = self.payment_days, 
		total_working_hours = self.total_working_hours, 
		hour_rate = self.hour_rate, 
		base_hour_rate = self.base_hour_rate, 
		gross_pay = self.gross_pay, 
		base_gross_pay = self.base_gross_pay, 
		gross_year_to_date = self.gross_year_to_date, 
		base_gross_year_to_date = self.base_gross_year_to_date, 
		custom_gross_arrears = self.custom_gross_arrears, 
		total_deduction = self.total_deduction, 
		base_total_deduction = self.base_total_deduction, 
		custom_bonus_rate = self.custom_bonus_rate, 
		custom_bonus_amount = self.custom_bonus_amount, 
		custom_total_deduction_arrears = self.custom_total_deduction_arrears, 
		net_pay = self.net_pay, 
		base_net_pay = self.base_net_pay, 
		rounded_total = self.rounded_total, 
		base_rounded_total = self.base_rounded_total, 
		custom_net_pay_arrears = self.custom_net_pay_arrears, 
		year_to_date = self.year_to_date, 
		base_year_to_date = self.base_year_to_date, 
		month_to_date = self.month_to_date, 
		base_month_to_date = self.base_month_to_date, 
		total_in_words = self.total_in_words, 
		base_total_in_words = self.base_total_in_words, 
		ctc = self.ctc, 
		income_from_other_sources = self.income_from_other_sources, 
		total_earnings = self.total_earnings, 
		non_taxable_earnings = self.non_taxable_earnings, 
		standard_tax_exemption_amount = self.standard_tax_exemption_amount, 
		tax_exemption_declaration = self.tax_exemption_declaration, 
		deductions_before_tax_calculation = self.deductions_before_tax_calculation, 
		annual_taxable_amount = self.annual_taxable_amount, 
		income_tax_deducted_till_date = self.income_tax_deducted_till_date, 
		current_month_income_tax = self.current_month_income_tax, 
		future_income_tax_deductions = self.future_income_tax_deductions, 
		total_income_tax = self.total_income_tax, 
		bank_name = self.bank_name, 
		bank_account_no = self.bank_account_no, 
		doctype = "Arrear Slip", 
		timesheets = self.timesheets, 
		leave_details = self.leave_details,
		earnings = self.earnings,
		deductions = self.deductions
	))


	for e in self.earnings:
		
		if e.salary_component in earned:
			arr_slip.append("earnings", {
				"salary_component": e.salary_component,
				"amount": e.amount,
				"parent": arr_slip.name,
				"doctype": "Arrear Detail"
			})
	for e in self.deductions:
		
		if e.salary_component in deducted:
			arr_slip.append("deductions", {
				"salary_component": e.salary_component,
				"amount": e.amount,
				"parent": arr_slip.name,
				"doctype": "Arrear Detail"
			})		
	
	for e in self.earnings:
		if e.salary_component in earned:
			e.custom_arrears_difference = earned[e.salary_component] * k
			final_gross += earned[e.salary_component] * k
	for e in self.deductions:
		if e.salary_component in deducted:
			e.custom_arrears_difference = deducted[e.salary_component] * k
			final_deduction += deducted[e.salary_component] * k

	arr_slip.gross = final_gross
	arr_slip.total_deductions = final_deduction
	arr_slip.net_pay = final_gross - final_deduction
	arr_slip.base_net_pay = final_gross - final_deduction
	arr_slip.rounded_total = round(final_gross - final_deduction)

	arr_slip.insert()
	self.custom_gross_arrears = final_gross
	self.custom_total_deduction_arrears = final_deduction

	# for e in self.earnings:
	# 	if e.salary_component in earned:
	# 		e.custom_arrears_difference = earned[e.salary_component]
	# for e in self.deductions:
	# 	if e.salary_component in deducted:
	# 		e.custom_arrears_difference = deducted[e.salary_component]