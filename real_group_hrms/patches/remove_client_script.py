import frappe


def execute():
    frappe.db.delete("Client Script")
