import frappe
from frappe import _
from frappe.utils import today


def validate(doc, method=None):
    validate_allocated_earned_leave(doc)


def validate_allocated_earned_leave(doc):
    old_configuration = doc.get_doc_before_save()

    if (
        old_configuration
        and old_configuration.is_earned_leave
        and old_configuration.max_leaves_allowed > doc.max_leaves_allowed
    ):
        earned_leave_allocation_exists = frappe.db.exists(
            "Leave Allocation",
            {"leave_type": doc.name, "from_date": ("<=", today()), "to_date": (">=", today())},
            cache=True,
        )
        if earned_leave_allocation_exists:
            frappe.msgprint(
                title=_("Leave Allocation Exists"),
                msg=_(
                    "Reducing maximum leaves allowed after allocation may cause scheduler to allocate incorrect number of earned leaves. Proceed with caution."
                ),
            )
