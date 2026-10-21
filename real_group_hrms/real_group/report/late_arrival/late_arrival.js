function getYearList(range = 3) {
	const currentYear = new Date().getFullYear();
	const years = [];

	for (let i = currentYear - range; i <= currentYear + range; i++) {
		years.push(i);
	}

	return years;
}


frappe.query_reports["Late Arrival"] = {
	filters: [
		{
			"fieldname": "company",
			"fieldtype": "Link",
			"options": "Company",
			"label": "Company",
			"reqd": 0,
			"on_change": function () {
				frappe.query_report.set_filter_value("department", null);
				frappe.query_report.set_filter_value("employee", null);
			}
		},
		{
			"fieldname": "branch",
			"fieldtype": "Link",
			"options": "Branch",
			"label": "Branch",
			"reqd": 1,
			"on_change": function () {
				frappe.query_report.set_filter_value("employee", null);
			}
		},
		{
			"fieldname": "division",
			"fieldtype": "Link",
			"options": "Division",
			"label": "Division"
		},

		{
			"fieldname": "department",
			"fieldtype": "Link",
			"options": "Department",
			"label": "Department",
			"get_query": function () {
				var company = frappe.query_report.get_filter_value("company");
				if (company) {
					return {
						filters: [
							["Department", "company", "=", company]
						]
					};
				}

				return {};
			}
		},
		{
			"fieldname": "employee",
			"fieldtype": "Link",
			"options": "Employee",
			"label": "Employee",
			"get_query": function () {
				var company = frappe.query_report.get_filter_value("company");
				var branch = frappe.query_report.get_filter_value("branch");
				var filters = [];

				if (company) {
					filters.push(["Employee", "company", "=", company]);
				}
				if (branch) {
					filters.push(["Employee", "branch", "=", branch]);
				}

				return { filters: filters };
			}
		},
		{
			"fieldname": "month",
			"fieldtype": "Select",
			"label": "Month",
			"options": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
			"reqd": 1
		},
		{
			"fieldname": "year",
			"fieldtype": "Select",
			"label": "Year",
			"options": getYearList(),
			"reqd": 1
		}
	]
}
