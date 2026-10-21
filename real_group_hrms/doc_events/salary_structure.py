import frappe
from frappe import _


def validate(doc, method=None):
	_validate_unique_components(doc, "earnings")
	_validate_unique_components(doc, "deductions")


def _validate_unique_components(doc, table_name):
	seen = {}
	for row in doc.get(table_name):
		component = row.salary_component
		if not component:
			continue
		if component in seen:
			frappe.throw(
				_("Row #{0}: Salary Component {1} is already added in Row #{2} of {3}. Each component can only be added once.").format(
					row.idx,
					frappe.bold(component),
					seen[component],
					frappe.bold(table_name.capitalize()),
				),
				title=_("Duplicate Salary Component"),
			)
		seen[component] = row.idx
