import frappe


MAX_ALLOWED_MIS_PUNCH_DAYS = 28


def validate(doc, method):
    value = doc.get("custom_allowed_mis_punch_days")
    doc.custom_allowed_mis_punch_days = validate_allowed_mis_punch_days(value)


def on_update(doc, method):
    if doc.has_value_changed("custom_holiday_list"):
        employees = frappe.get_all("Employee", filters={"branch": doc.name, "status": "Active"}, pluck="name")
        for e in employees:
            frappe.db.set_value("Employee", e, "holiday_list", doc.custom_holiday_list)


def get_two_digit_value(value):
    if value in (None, ""):
        return value

    digits = "".join(char for char in str(value) if char.isdigit())
    if not digits:
        return None

    return int(digits[:2])


def validate_allowed_mis_punch_days(value):
    value = get_two_digit_value(value)

    if value is not None and value > MAX_ALLOWED_MIS_PUNCH_DAYS:
        frappe.throw(frappe._("Maximum allowed MIS punch days is 28."))

    return value
