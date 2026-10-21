import frappe


INDEX_SPECS = (
    ("Employee", "idx_emp_branch_status_company", ("branch", "status", "company")),
    ("Employee", "idx_emp_company_branch_status_dept", ("company", "branch", "status", "department")),
    ("Employee", "idx_emp_company_branch_status_div", ("company", "branch", "status", "custom_division")),
    ("Employee", "idx_emp_branch_dept", ("branch", "department")),
    ("Employee", "idx_emp_branch_div", ("branch", "custom_division")),
    ("Employee", "idx_emp_company_branch_dept", ("company", "branch", "department")),
    ("Employee", "idx_emp_company_branch_div", ("company", "branch", "custom_division")),
    ("Employee Checkin", "idx_ec_attendance", ("attendance",)),
    ("Employee Checkin", "idx_ec_emp_attendance", ("employee", "attendance")),
    ("Employee Checkin", "idx_ec_emp_time", ("employee", "time")),
    ("Employee Checkin", "idx_ec_time_emp", ("time", "employee")),
    ("Employee Checkin", "idx_ec_emp_shift_start", ("employee", "shift_start")),
    ("Shift Assignment", "idx_sa_emp", ("employee",)),
    ("Attendance", "idx_att_emp_date_doc", ("employee", "attendance_date", "docstatus")),
    ("Attendance Request", "idx_ar_emp_doc_from_to", ("employee", "docstatus", "from_date", "to_date")),
    ("Attendance Request", "idx_ar_emp_doc_to_from", ("employee", "docstatus", "to_date", "from_date")),
    ("Holiday", "idx_holiday_parent_date", ("parent", "holiday_date")),
    ("Weekly Off Holiday", "idx_woh_parent_date", ("parent", "holiday_date")),
    ("Weekly Holiday Update Request", "idx_whur_emp_doc_valid", ("employee", "docstatus", "valid_from")),
    ("Incentive Log", "idx_il_emp_work_doc", ("employee", "work_date", "docstatus")),
    ("Compensatory Leave Request", "idx_clr_emp_work_doc", ("employee", "work_from_date", "work_end_date", "docstatus")),
    ("Short Leave", "idx_sl_emp_date_doc", ("employee", "for_date", "docstatus")),
)


def ensure_reprocess_indexes():
    for doctype, index_name, columns in INDEX_SPECS:
        if _has_index(doctype, index_name) or _has_equivalent_index(doctype, columns):
            continue
        frappe.db.add_index(doctype, list(columns), index_name=index_name)


def _has_index(doctype: str, index_name: str) -> bool:
    return bool(frappe.db.has_index(f"tab{doctype}", index_name))


def _has_equivalent_index(doctype: str, columns: tuple[str, ...]) -> bool:
    rows = frappe.db.sql(f"SHOW INDEX FROM `tab{doctype}`", as_dict=True)
    target = tuple(columns)
    indexes = {}
    for row in rows:
        key = row.get("Key_name")
        seq = int(row.get("Seq_in_index") or 0)
        col = row.get("Column_name")
        if not key or not seq or not col:
            continue
        indexes.setdefault(key, {})[seq] = col

    for parts in indexes.values():
        ordered = tuple(parts[i] for i in sorted(parts))
        if ordered == target:
            return True

    return False
