__version__ = "0.0.1"


def monkey_patch():
    from frappe.www import login

    from real_group_hrms.api.overrides.auth import send_login_link as custom_send_login_link
    from real_group_hrms.overrides.query_report_export import (
        build_xlsx_data_with_cell_styles,
        make_xlsx_with_cell_styles,
    )

    login.send_login_link = custom_send_login_link

    import hrms.hr.doctype.employee_checkin.employee_checkin as ec

    from real_group_hrms.overrides.employee_checkin import mark_attendance_and_link_log

    ec.mark_attendance_and_link_log = mark_attendance_and_link_log

    import hrms.hr.doctype.leave_policy_assignment.leave_policy_assignment as lpa

    from real_group_hrms.overrides.leave_policy_assignment import get_earned_leaves, get_leave_type_details
    from real_group_hrms.utils import check_effective_date

    lpa.get_leave_type_details = get_leave_type_details

    import hrms.hr.utils as hr_utils

    hr_utils.get_earned_leaves = get_earned_leaves
    hr_utils.check_effective_date = check_effective_date

    import hrms.hr.doctype.leave_application.leave_application as la

    from real_group_hrms.api.overrides.leave_application import (
        get_holidays,
        get_leave_balance_on,
        get_leave_details,
        get_number_of_leave_days,
    )

    la.get_leave_details = get_leave_details
    la.get_holidays = get_holidays
    la.get_number_of_leave_days = get_number_of_leave_days
    la.get_leave_balance_on = get_leave_balance_on

    from frappe.desk import query_report
    from frappe.utils import xlsxutils

    query_report.build_xlsx_data = build_xlsx_data_with_cell_styles
    xlsxutils.make_xlsx = make_xlsx_with_cell_styles


monkey_patch()  # nosemgrep
