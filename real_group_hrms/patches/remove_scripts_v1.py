import frappe


def execute():
    names = [
        "Leave Application On Cancel",
        "Leave Application Assignment",
        "Attendance Half Type Update",
        "Leave Application - Before Delete",
        "Leave Application Leave Balance Validation",
        "Leave Application",
        "Update Leave Allocation",
        "Leave Application Validation",
        "Set Employee Attendance ID",
    ]
    frappe.db.delete("Server Script", {"name": ("in", names)})
