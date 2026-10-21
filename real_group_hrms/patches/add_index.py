import frappe 

def execute():
    add_index = [
        ("Attendance", ["attendance_date"]),
        ("Attendance", ["attendance_request"]),
        ("Attendance", ["employee"]),
        ("Attendance", ["custom_reprocess_reference"]),
        ("Attendance", ["leave_application"]),
        ("Employee Checkin", ["attendance"])
    ]
    for doctype,field in add_index:
        frappe.db.add_index(doctype, field)
