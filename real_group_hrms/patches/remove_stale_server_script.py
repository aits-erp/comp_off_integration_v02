import frappe


def execute():
    names = [
        "Employee Checkin - Before Delete",
        "SMS for Late Check In",
        "Comp-off allocation on Extra Worked Hours",
        "Attendance - Before Save",
        "Attendance - Before Insert",
        "Attendance - Before Delete",
        "Comp-off on Extra Worked Hours",
        "Attendance Request - Before Insert",
        "Set Default Shift - Attendance Request",
        "Attendance Request Before Delete",
        "Attendance Request - Before Submit",
        "Attendance Request on Cancel",
        "Attendance Request - Before Delete",
        "Attendance Request Validate",
        "Attendance Request Self Approve Validation",
        "Short Leave Validation from Grade",
        "Leave Application Self Approve Validation",
        "Setting up Identifier Shift Type",
    ]
    frappe.db.delete("Server Script", {"name": ("in", names)})
