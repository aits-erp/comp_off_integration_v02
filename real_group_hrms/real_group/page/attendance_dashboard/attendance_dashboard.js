
frappe.provide("frappe.dashboards");
frappe.provide("frappe.dashboards.chart_sources");


frappe.pages['attendance-dashboard'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Attendance',
		single_column: true
	});

	let attendance_dashboard = new AttendanceDashboard(wrapper);

	wrapper = $(wrapper).find('.layout-main');
	wrapper.append(`<div id="chart"></div>`);

}

class AttendanceDashboard {
	constructor(wrapper) {
		this.wrapper = wrapper;
		this.setup();
		// this.render_charts();
		// this.get_data();
	}

	setup() {
		var me = this;

		(this.company_field = this.wrapper.page.add_field({
			fieldtype: "Link",
			fieldname: "company",
			options: "Company",
			label: __("Company"),
			reqd: 1,
			default: frappe.defaults.get_user_default("company"),
			change: function () {
				me.company = this.value || frappe.defaults.get_user_default("company");
			},
		})),
			(this.branch_field = this.wrapper.page.add_field({
				fieldtype: "Link",
				fieldname: "branch",
				options: "Branch",
				label: __("Branch"),
				change: function () {
					me.branch = this.value;
				},
			})),
			(this.department_field = this.wrapper.page.add_field({
				fieldtype: "Link",
				fieldname: "department",
				options: "Department",
				label: __("Department"),
				change: function () {
					me.department = this.value;
				},
			})),
			(this.employee_field = this.wrapper.page.add_field({
				fieldtype: "Link",
				fieldname: "employee",
				options: "Employee",
				label: __("Employee"),
				change: function () {
					me.employee = this.value;
				},
			})),
			(this.month_field = this.wrapper.page.add_field({
				fieldtype: "Select",
				fieldname: "month",
				options: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
				label: __("Month"),
				reqd: 1,
				change: function () {
					me.month = this.value;
				},
			})),
			(this.year_field = this.wrapper.page.add_field({
				fieldtype: "Select",
				fieldname: "year",
				options: ['2023', '2024'],
				label: __("Year"),
				reqd: 1,
				change: function () {
					me.year = this.value;
					me.get_data()
				},
			})),

			(this.refresh_btn = this.wrapper.page.set_primary_action(
				__("Refresh"),
				function () {
					me.get_data();
				},
				"refresh"
			)),

			(this.elements = {
				layout: $(this.wrapper).find(".layout-main"),
			});

		this.elements.no_data = $('<div class="alert alert-warning">' + __("No Data") + "</div>")
			.toggle(false)
			.appendTo(this.elements.layout);

		this.elements.attendance_dashboard_wrapper = $('<div class="attendance-dashboard-wrapper"></div>').appendTo(
			this.elements.layout
		);


		this.company = frappe.defaults.get_user_default("company");
		this.refresh_btn.on("click", function () {
			me.get_data(this);
		});

	}

	get_data(btn) {
		var me = this;
		if (!this.company) {
			frappe.throw(__("Please Select a Company."));
		}
		if (!this.month) {
			frappe.throw(__("Please Select a Month."));
		}
		if (!this.year) {
			frappe.throw(__("Please Select a Year."));
		}
		const $parent = me.elements.attendance_dashboard_wrapper;
		frappe.call({
			method: 'real_group_hrms.real_group.page.attendance_dashboard.attendance_dashboard.get_card_details',
			args: {
				company: me.company,
				month: me.month,
				year: me.year,
				branch: me.branch,
				department: me.department,
				employee: me.employee,
			},
			btn: btn,
			callback: function (r) {
				if (!r.exc) {
					let main_html = r.message;
					if (main_html == "empty") {
						$parent.html(__("No data for this period"));
					} else {
						$parent.html(`
								${main_html} 
								<div id="attendance_count_chart"></div>
								`)

						setTimeout(() => {
							me.get_charts();
						}, 1000);
					}
				}
			},
		});
	}


	// render_charts() {
	// 	// var me = this;
	// 	// const $parent = me.elements.attendance_dashboard_wrapper;
	// 	// $parent.html('<div id="chart"></div>')
	// 	return this.get_charts()
	// }

	get_charts() {

		var me = this;

		frappe.call({
			method: 'real_group_hrms.real_group.page.attendance_dashboard.attendance_dashboard.get_chart_details',
			args: {
				company: me.company,
				month: me.month,
				year: me.year,
				branch: me.branch,
				department: me.department,
				employee: me.employee,
			},
			callback: function (r) {
				if (!r.exc) {
					let result = r.message;

					// const data = {
					// 	labels: ["12am-3am", "3am-6pm", "6am-9am", "9am-12am",
					// 		"12pm-3pm", "3pm-6pm", "6pm-9pm", "9am-12am"
					// 	],
					// 	datasets: [
					// 		{
					// 			name: "Some Data", type: "bar",
					// 			values: [25, 40, 30, 35, 8, 52, 17, -4]
					// 		},
					// 		{
					// 			name: "Another Set", type: "line",
					// 			values: [25, 50, -10, 15, 18, 32, 27, 14]
					// 		}
					// 	]
					// }
					const chart = new frappe.Chart("#attendance_count_chart", {
						title: "Attendance Count",
						data: result,
						type: 'line',
						height: 250,
						colors: ['#7cd6fd', '#743ee2']
					});
					chart.draw();
				}
			},
		});



	}
}


