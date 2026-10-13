import frappe
from frappe import _


def before_insert(doc, method=None):
    if doc.company or not doc.appraisal_cycle:
        return

    doc.company = frappe.db.get_value("Appraisal Cycle", doc.appraisal_cycle, "company")


def before_submit(doc, method=None):
    if not frappe.db.exists("Employee Performance Feedback", {"appraisal": doc.name, "docstatus": 1}):
        frappe.throw(_("Please submit Employee Performance Feedback before submitting Appraisal."))
