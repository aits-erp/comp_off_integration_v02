import frappe
from frappe import _
from frappe.utils import add_days, get_url_to_list
from hrms.hr.doctype.compensatory_leave_request.compensatory_leave_request import CompensatoryLeaveRequest
from hrms.hr.utils import create_additional_leave_ledger_entry, get_leave_period


class CompensatoryLeaveRequestOverride(CompensatoryLeaveRequest):
    def validate_holidays(self):
        pass

    def validate_attendance(self):
        pass

    def on_submit(self):
        company = frappe.db.get_value("Employee", self.employee, "company")

        date_difference = self.credit

        comp_leave_valid_from = add_days(self.work_end_date, 1)
        leave_period = get_leave_period(comp_leave_valid_from, comp_leave_valid_from, company)
        if leave_period:
            leave_allocation = self.get_existing_allocation_for_period(leave_period)
            if leave_allocation:
                leave_allocation.new_leaves_allocated += date_difference
                leave_allocation.validate()
                leave_allocation.db_set("new_leaves_allocated", leave_allocation.total_leaves_allocated)
                leave_allocation.db_set("total_leaves_allocated", leave_allocation.total_leaves_allocated)

                # generate additional ledger entry for the new compensatory leaves off
                create_additional_leave_ledger_entry(leave_allocation, date_difference, comp_leave_valid_from)

            else:
                leave_allocation = self.create_leave_allocation(leave_period, date_difference)
            self.db_set("leave_allocation", leave_allocation.name)
        else:
            comp_leave_valid_from = frappe.bold(frappe.utils.format_date(comp_leave_valid_from))
            msg = _("This compensatory leave will be applicable from {0}.").format(comp_leave_valid_from)
            msg += " " + _(
                "Currently, there is no {0} leave period for this date to create/update leave allocation."
            ).format(frappe.bold(_("active")))
            msg += "<br><br>" + _("Please create a new {0} for the date {1} first.").format(
                f"""<a href='{get_url_to_list("Leave Period")}'>Leave Period</a>""",
                comp_leave_valid_from,
            )
            frappe.throw(msg, title=_("No Leave Period Found"))

    def on_cancel(self):
        if self.leave_allocation:
            date_difference = self.credit

            leave_allocation = frappe.get_doc("Leave Allocation", self.leave_allocation)
            if leave_allocation:
                leave_allocation.new_leaves_allocated -= date_difference
                if leave_allocation.new_leaves_allocated <= 0:
                    leave_allocation.new_leaves_allocated = 0
                leave_allocation.validate()
                leave_allocation.db_set("new_leaves_allocated", leave_allocation.total_leaves_allocated)
                leave_allocation.db_set("total_leaves_allocated", leave_allocation.total_leaves_allocated)

                # create reverse entry on cancelation
                create_additional_leave_ledger_entry(
                    leave_allocation, date_difference * -1, add_days(self.work_end_date, 1)
                )
