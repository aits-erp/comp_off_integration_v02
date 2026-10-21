import frappe
from frappe.utils import getdate


def process():
    date = getdate()
    requests = frappe.get_all(
        "Weekly Holiday Update Request", filters={"valid_from": ("=", date), "docstatus": 1}, pluck="name"
    )
    for req in requests:
        doc = frappe.get_doc("Weekly Holiday Update Request", req)
        doc.update_weekly_off_in_employee()
        frappe.db.commit()
