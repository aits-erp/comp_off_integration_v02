import frappe
from frappe.utils import getdate
from hrms.hr.doctype.employee_transfer.employee_transfer import EmployeeTransfer
from hrms.hr.doctype.leave_ledger_entry.leave_ledger_entry import expire_allocation
from hrms.hr.utils import update_employee_work_history


class EmployeeTransferOverride(EmployeeTransfer):
    def on_submit(self):
        employee = frappe.get_doc("Employee", self.employee)
        if self.create_new_employee_id:
            new_employee = frappe.copy_doc(employee)
            new_employee.name = None
            new_employee.employee_number = None
            new_employee = update_employee_work_history(new_employee, self.transfer_details, date=self.transfer_date)
            if self.new_company and self.company != self.new_company:
                new_employee.internal_work_history = []
                new_employee.date_of_joining = self.transfer_date
                new_employee.company = self.new_company

            new_employee.user_id = None
            new_employee.update({"attendance_device_id": ""})
            new_employee.flags.ignore_aadhar_validation = True
            new_employee.insert()

            # Update attendance_device_id after insert, since it is same as employee name
            new_employee.db_set("attendance_device_id", new_employee.name)

            self.db_set("new_employee_id", new_employee.name)
            # relieve the old employee
            employee.db_set("relieving_date", self.transfer_date)
            employee.db_set("status", "Left")
        else:
            employee = update_employee_work_history(employee, self.transfer_details, date=self.transfer_date)
            if self.new_company and self.company != self.new_company:
                employee.company = self.new_company
                employee.date_of_joining = self.transfer_date
            employee.save()

        self.leave_allocation_on_transfer()

    def leave_allocation_on_transfer(self):
        leave_info = self.custom_employee_leave
        if not leave_info:
            return
        for leave in leave_info:
            allocation = self.get_employee_allocation(leave.existing_leave_type)
            if leave.expire:
                if allocation:
                    allocation = frappe.get_doc("Leave Allocation", allocation)
                    expire_allocation(allocation, self.transfer_date)
            else:
                leave_to_transfer = leave.number_of_leaves
                leave_type_to_allocate = leave.new_leave_type

                if not leave_type_to_allocate or leave_to_transfer <= 0:
                    frappe.throw(
                        frappe._(
                            "Please specify valid Leave Type and Number of Leaves to transfer for Employee: {0}"
                        ).format(self.employee)
                    )
                if not allocation:
                    frappe.throw(
                        frappe._("No active Leave Allocation found for Leave Type: {0} for Employee: {1}").format(
                            leave.existing_leave_type, self.employee
                        )
                    )
                validity = frappe.db.get_value("Leave Allocation", allocation, ["from_date", "to_date"], as_dict=1)
                from_date = getdate(validity.from_date)
                to_date = getdate(validity.to_date)
                allocation_doc = frappe.get_doc(
                    {
                        "doctype": "Leave Allocation",
                        "employee": self.new_employee_id,
                        "leave_type": leave_type_to_allocate,
                        "from_date": from_date,
                        "to_date": to_date,
                        "new_leaves_allocated": leave_to_transfer,
                    }
                )
                allocation_doc.flags.ignore_permissions = True
                allocation_doc.insert()
                allocation_doc.submit()
                allocation = frappe.get_doc("Leave Allocation", allocation)
                expire_allocation(allocation, self.transfer_date)

    def get_employee_allocation(self, leave_type: str):
        return frappe.db.get_value(
            "Leave Allocation",
            {
                "employee": self.employee,
                "docstatus": 1,
                "expired": 0,
                "from_date": ["<=", self.transfer_date],
                "to_date": [">=", self.transfer_date],
                "leave_type": leave_type,
            },
            "name",
        )
