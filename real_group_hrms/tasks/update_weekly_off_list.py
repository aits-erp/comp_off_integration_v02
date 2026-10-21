import frappe
from frappe.utils import add_years, getdate


def process():
    offs = frappe.get_all("Weekly Off List", filters={"to_date": getdate()}, fields=["*"])

    to_date = add_years(getdate(), 1)
    for off in offs:
        doc = frappe.get_doc("Weekly Off List", off.name)
        doc.to_date = to_date
        doc.get_weekly_off_dates()
        doc.save()
