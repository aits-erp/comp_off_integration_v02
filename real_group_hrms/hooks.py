app_name = "real_group_hrms"
app_title = "REAL Group HRMS"
app_publisher = "REAL Group"
app_description = "HRMS Customized for REAL Group"
app_email = "itadmin@realgroup.org"
app_license = "mit"
# required_apps = []

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/real_group_hrms/css/real_group_hrms.css"
# app_include_js = "/assets/real_group_hrms/js/real_group_hrms.js"

# include js, css files in header of web template
# web_include_css = "/assets/real_group_hrms/css/real_group_hrms.css"
# web_include_js = "/assets/real_group_hrms/js/real_group_hrms.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "real_group/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {
    "User": "public/js/form/user.js",
    "Leave Application": "public/js/form/leave_application.js",
    "Employee": "public/js/form/employee.js",
    "Employee Performance Feedback": "public/js/form/employee_performance_feedback.js",
    "Appraisal Template": "public/js/form/appraisal_template.js",
    "Employee Grade": "public/js/form/employee_grade.js",
    "Attendance Request": "public/js/form/attendance_request.js",
    "Salary Structure": "public/js/form/salary_structure.js",
    "Salary Structure Assignment": "public/js/form/salary_structure_assignment.js",
    "Interview": "public/js/form/interview.js",
    "Compensation Matrix": "public/js/form/compensation_matrix.js",
    "Arrear Slip": "public/js/form/arrear_slip.js",
    "Medical History": "public/js/form/medical_history.js",
    "Employee Onboarding Form": "public/js/form/employee_onboarding_form.js",
    "Additional Salary": "public/js/form/additional_salary.js",
    "Expense Claim": "public/js/form/expense_claim.js",
    "Skip Loan Installment": "public/js/form/skip_loan_installment.js",
    "Reprocess Attendance": "public/js/form/reprocess_attendance.js",
    "Appointment Letter": "public/js/form/appointment_letter.js",
    "Real Group User": "public/js/form/real_group_user.js",  # TODO: Check if this is required
    "Salary Slip": "public/js/form/salary_slip.js",
    "Shift Type": "public/js/form/shift_type.js",
    "Leave Type": "public/js/form/leave_type.js",
    "Employee Transfer": "public/js/form/employee_transfer.js",
    "Employee Checkin": "public/js/form/employee_checkin.js",
    "Training Event": "public/js/form/training_event.js",
    "Branch": "public/js/form/branch.js",
}
doctype_list_js = {
    "Leave Application": "public/js/list/leave_application.js",
    "Attendance": "public/js/list/attendance.js",
    "Employee Checkin": "public/js/list/employee_checkin.js",
}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "real_group/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
jinja = {"methods": ["real_group_hrms.real_group.utils.get_qr_code"]}

# Installation
# ------------

# before_install = "real_group_hrms.install.before_install"
# after_install = "real_group_hrms.install.after_install"
after_migrate = "real_group_hrms.migration.ensure_reprocess_indexes"

on_session_creation = [
    "real_group_hrms.api.session.mark_pwa_session",
]

# Uninstallation
# ------------

# before_uninstall = "real_group_hrms.uninstall.before_uninstall"
# after_uninstall = "real_group_hrms.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "real_group_hrms.utils.before_app_install"
# after_app_install = "real_group_hrms.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "real_group_hrms.utils.before_app_uninstall"
# after_app_uninstall = "real_group_hrms.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "real_group_hrms.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
#     "Event": "frappe.desk.doctype.event.event.has_permission",
# }
has_permission = {
    "Notification Settings": "real_group_hrms.overrides.notification_settings.has_permission",
}

# DocType Class
# ---------------
# Override standard doctype classes

override_doctype_class = {
    "Notification Settings": "real_group_hrms.overrides.notification_settings.NotificationSettingsOverride",
    "User": "real_group_hrms.overrides.user.UserOverride",
    "Employee Checkin": "real_group_hrms.overrides.employee_checkin.EmployeeCheckinOverride",
    "Compensatory Leave Request": "real_group_hrms.overrides.compensatory_leave_request.CompensatoryLeaveRequestOverride",
    "Leave Application": "real_group_hrms.overrides.leave_application.LeaveApplicationOverride",
    "Leave Policy Assignment": "real_group_hrms.overrides.leave_policy_assignment.LeavePolicyAssignmentOverride",
    "Leave Allocation": "real_group_hrms.overrides.leave_allocation.LeaveAllocationOverride",
    "Attendance Request": "real_group_hrms.overrides.attendance_request.AttendanceRequestOverride",
    "Employee Transfer": "real_group_hrms.overrides.employee_transfer.EmployeeTransferOverride",
    "Salary Slip": "real_group_hrms.overrides.salary_slip.SalarySlipOverride",
    "Appraisal": "real_group_hrms.overrides.appraisal.AppraisalOverride",
}

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

doc_events = {
    "Appraisal": {
        "before_insert": "real_group_hrms.doc_events.appraisal.before_insert",
        "before_submit": "real_group_hrms.doc_events.appraisal.before_submit",
    },
    "Employee": {
        "autoname": "real_group_hrms.doc_events.employee.autoname",
        "after_insert": [
            "real_group_hrms.real_group.integration.create_employee",
            "real_group_hrms.doc_events.employee.after_insert",
            "real_group_hrms.real_group.integration.update_employee",
        ],
        "on_update": [
            "real_group_hrms.doc_events.employee.on_update",
            "real_group_hrms.real_group.integration.enqueue_update_employee",
        ],
        "validate": ["real_group_hrms.doc_events.employee.validate"],
    },
    "Holiday List": {
        "validate": "real_group_hrms.doc_events.holiday_list.validate",
    },
    "Shift Type": {"validate": ["real_group_hrms.doc_events.shift_type.validate"]},
    "Employee Checkin": {
        "validate": "real_group_hrms.doc_events.employee_checkin.validate",
        "after_insert": [
            "real_group_hrms.doc_events.employee_checkin.after_insert",
        ],
        "before_insert": [
            "real_group_hrms.doc_events.employee_checkin.before_insert",
        ],
        "before_save": ["real_group_hrms.doc_events.employee_checkin.before_save"],
    },
    "Attendance Request": {
        "validate": ["real_group_hrms.doc_events.attendace_request.validate"],
        "before_cancel": ["real_group_hrms.doc_events.attendace_request.before_cancel"],
        "before_delete": ["real_group_hrms.doc_events.attendace_request.before_delete"],
        "on_cancel": ["real_group_hrms.doc_events.attendace_request.on_cancel"],
        "on_submit": ["real_group_hrms.doc_events.attendace_request.on_submit"],
    },
    "Attendance": {
        "validate": ["real_group_hrms.doc_events.attendance.validate"],
        "on_submit": ["real_group_hrms.doc_events.attendance.on_submit"],
        "before_cancel": ["real_group_hrms.doc_events.attendance.before_cancel"],
        "before_delete": ["real_group_hrms.doc_events.attendance.before_delete"],
        "on_cancel": ["real_group_hrms.doc_events.attendance.on_cancel"],
    },
    "User": {
        "validate": ["real_group_hrms.doc_events.user.validate"],
        "after_insert": ["real_group_hrms.real_group.integration.create_user"],
        "on_update": ["real_group_hrms.real_group.integration.update_user"],
        "update_password": ["real_group_hrms.real_group.integration.update_user_password"],
    },
    "Salary Structure": {
        "validate": ["real_group_hrms.doc_events.salary_structure.validate"],
    },
    "Salary Structure Assignment": {
        "before_save": [
            "real_group_hrms.doc_events.salary_structure_assignment.before_save",
        ],
        "before_submit": ["real_group_hrms.real_group.integration.insert_salary_structure"],
    },
    "Salary Slip": {
        "on_submit": ["real_group_hrms.real_group.integration.create_salary_slip"],
        "on_cancel": ["real_group_hrms.real_group.integration.cancel_salary_slip"],
        #    "before_save": ["real_group_hrms.real_group.arrears.arrears_in_current_sal_slip"]
    },
    "Leave Type": {
        "validate": ["real_group_hrms.doc_events.leave_type.validate"],
    },
    "Leave Application": {
        "validate": "real_group_hrms.doc_events.leave_application.validate",
        "before_cancel": "real_group_hrms.doc_events.leave_application.before_cancel",
        "before_delete": "real_group_hrms.doc_events.leave_application.before_delete",
    },
    "Employee Grade": {
        "validate": "real_group_hrms.doc_events.employee_grade.validate",
    },
    "Training Event": {
        "validate": "real_group_hrms.doc_events.training_event.validate",
    },
    "Branch": {
        "validate": "real_group_hrms.doc_events.branch.validate",
        "on_update": "real_group_hrms.doc_events.branch.on_update",
    },
}

# Scheduled Tasks
# ---------------

scheduler_events = {
    "cron": {
        "*/2 * * * *": ["real_group_hrms.tasks.process_employee_checkin.process"],
        # TODO: This will be removed, since not being used.
        # "* * * * *": ["real_group_hrms.tasks.pull_attendance_log.pull_data_from_postgre"],
        "0 9 * * *": [
            "real_group_hrms.tasks.process_attendance_for_no_checkin_applicable.process",
            "real_group_hrms.real_group.notifications.send_birthday_wishes",
            "real_group_hrms.real_group.doctype.gate_pass.gate_pass.expire_gate_passes",
        ],
        "* 0 * * *": [
            "real_group_hrms.tasks.update_weekly_off_in_employee.process",
            "real_group_hrms.tasks.update_weekly_off_list.process",
        ],
        "0 4 10 * *": ["real_group_hrms.tasks.expire_coff.expire_unused_comp_off"],
        "0 3 * * *": ["real_group_hrms.tasks.process_attendance.process"],
        "59 23 * * *": ["real_group_hrms.tasks.process_attendance_for_single_checkin.process"],
        "0 14 * * *": ["real_group_hrms.utils.allocate_leaves_for_worked_days"],
        "5 0 2 * *": ["real_group_hrms.real_group.attendance.process_attendance_for_last_day_of_month"],
    },
}

# scheduler_events = {
# 	"all": [
# 		"real_group_hrms.tasks.all"
# 	],
# 	"daily": [
# 		"real_group_hrms.tasks.daily"
# 	],
# 	"hourly": [
# 		"real_group_hrms.tasks.hourly"
# 	],
# 	"weekly": [
# 		"real_group_hrms.tasks.weekly"
# 	],
# 	"monthly": [
# 		"real_group_hrms.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "real_group_hrms.install.before_tests"

# Overriding Methods
# ------------------------------
#
override_whitelisted_methods = {
    "frappe.core.doctype.user.user.update_password": "real_group_hrms.api.overrides.user.update_user_password",
    "hrms.hr.doctype.leave_application.leave_application.get_leave_details": "real_group_hrms.api.overrides.leave_application.get_leave_details",
    "hrms.hr.doctype.leave_application.leave_application.get_holidays": "real_group_hrms.api.overrides.leave_application.get_holidays",
    "hrms.hr.doctype.leave_application.leave_application.get_number_of_leave_days": "real_group_hrms.api.overrides.leave_application.get_number_of_leave_days",
    "hrms.hr.doctype.leave_application.leave_application.get_leave_balance_on": "real_group_hrms.api.overrides.leave_application.get_leave_balance_on",
}
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "real_group_hrms.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["real_group_hrms.utils.before_request"]
# after_request = ["real_group_hrms.utils.after_request"]

# Job Events
# ----------
# before_job = ["real_group_hrms.utils.before_job"]
# after_job = ["real_group_hrms.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"real_group_hrms.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }


fixtures = [
    {"dt": "Custom Field", "filters": [["module", "=", "Real Group"]]},
    {"dt": "Report", "filters": [["module", "=", "Real Group"]]},
    {"dt": "Print Format", "filters": [["module", "=", "Real Group"]]},
    {"dt": "Server Script", "filters": [["module", "=", "Real Group"]]},
    {"dt": "Property Setter", "filters": [["module", "=", "Real Group"]]},
    {"dt": "Workflow"},
    {"dt": "Workflow State"},
    {"dt": "Workflow Action Master"},
    {"dt": "List View Settings"},
]

persistent_cache_keys = [
    "reprocess-attendance-*",  # Attendance Reprocessing related caches
]
