import frappe

custom_fields = {
    "Shift Type": [
        "custom_present_threshold",
        "custom_half_day_threshold",
        "custom_absent_threshold",
        "custom_section_break_nntim",
        "custom_shift_start_grace_time",
        "custom_actual_start_time",
    ],
    "Employee Grade": [
        "custom_check_in_grace_time",
        "custom_section_break_ojbku",
        "custom_present_threshold_hrs",
        "custom_absent_threshold_hrs",
        "custom_half_day_threshold_hrs",
        "custom_check_out_grace_time",
        "custom_section_break_hh6ng",
        "custom_early_exit_grace_period",
        "custom_working_hours_threshold_for_present",
        "custom_working_hours_threshold_for_half_day",
        "custom_working_hours_threshold_for_absent",
        "custom_description",
    ],
}


def execute():
    for doctype, fields in custom_fields.items():
        frappe.db.delete("Custom Field", {"dt": doctype, "fieldname": ("in", fields)})
