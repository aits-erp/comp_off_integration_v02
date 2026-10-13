import frappe
from frappe.utils import get_link_to_form


def validate(doc, method=None):
    validate_username(doc)


def validate_username(doc):
    exists = frappe.db.exists("User", {"username": ["like", doc.username], "name": ["!=", doc.name]})
    if exists:
        frappe.throw(
            frappe._("Username {0} already used by another user {1}.").format(
                doc.username, get_link_to_form("User", exists)
            )
        )
