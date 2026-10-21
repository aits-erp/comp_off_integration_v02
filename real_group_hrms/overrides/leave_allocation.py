import frappe
from frappe import _
from frappe.utils import flt, get_link_to_form
from hrms.hr.doctype.leave_allocation.leave_allocation import (
    LeaveAllocation,
    create_leave_ledger_entry,
    get_approved_leaves_for_period,
    get_carry_forwarded_leaves,
)


class LeaveAllocationOverride(LeaveAllocation):
    @frappe.whitelist()
    def set_total_leaves_allocated(self):
        self.unused_leaves = flt(
            get_carry_forwarded_leaves(self.employee, self.leave_type, self.from_date, self.carry_forward),
            self.precision("unused_leaves"),
        )

        self.total_leaves_allocated = flt(
            flt(self.unused_leaves) + flt(self.new_leaves_allocated),
            self.precision("total_leaves_allocated"),
        )

        self.limit_carry_forward_based_on_max_allowed_leaves()

        if self.carry_forward:
            self.set_carry_forwarded_leaves_in_previous_allocation()

        leave_type = frappe.get_doc("Leave Type", self.leave_type)
        if (
            not self.total_leaves_allocated
            and not leave_type.is_earned_leave
            and not leave_type.is_compensatory
            and not leave_type.custom_calculate_based_on_working_days
        ):
            frappe.throw(_("Total leaves allocated is mandatory for Leave Type {0}").format(self.leave_type))

    def validate_earned_leave_update(self):
        leave_type = frappe.db.get_value(
            "Leave Type", self.leave_type, ["is_earned_leave", "custom_calculate_based_on_working_days"]
        )
        is_earned_leave = leave_type[0]
        based_on_working_days = leave_type[1]
        if self.leave_policy_assignment and is_earned_leave and not based_on_working_days:
            msg = _("Cannot update allocation for {0} after submission").format(frappe.bold(_("Earned Leaves")))
            msg += "<br><br>"
            msg += _(
                "Earned Leaves are auto-allocated via scheduler based on the annual allocation set in the Leave Policy: {0}"
            ).format(get_link_to_form("Leave Policy", self.leave_policy))
            frappe.throw(msg, title=_("Not Allowed"))

    def validate_against_leave_applications(self):
        leaves_taken = get_approved_leaves_for_period(self.employee, self.leave_type, self.from_date, self.to_date)
        if flt(leaves_taken) > flt(self.total_leaves_allocated):
            if frappe.db.get_value("Leave Type", self.leave_type, "allow_negative"):
                frappe.msgprint(
                    _(
                        "Note: Total allocated leaves {0} shouldn't be less than already approved leaves {1} for the period"
                    ).format(self.total_leaves_allocated, leaves_taken)
                )

    # nosemgrep: frappe-semgrep-rules.rules.frappe-modifying-but-not-comitting
    def on_update_after_submit(self):
        is_based_on_working_days = frappe.db.get_value(
            "Leave Type", self.leave_type, "custom_calculate_based_on_working_days"
        )
        if self.has_value_changed("new_leaves_allocated") or is_based_on_working_days:
            self.validate_earned_leave_update()
            self.validate_against_leave_applications()

            # recalculate total leaves allocated

            if is_based_on_working_days:
                self.total_leaves_allocated += flt(self.new_leaves_allocated)
            else:
                self.total_leaves_allocated = flt(self.unused_leaves) + flt(self.new_leaves_allocated)
            self.validate_leave_days_and_dates()

            leaves_to_be_added = flt(
                (self.new_leaves_allocated - self.get_existing_leave_count()),
                self.precision("new_leaves_allocated"),
            )

            args = {
                "leaves": leaves_to_be_added if not is_based_on_working_days else flt(self.new_leaves_allocated),
                "from_date": self.from_date,
                "to_date": self.to_date,
                "is_carry_forward": 0,
            }
            create_leave_ledger_entry(self, args, True)
            self.db_update()
