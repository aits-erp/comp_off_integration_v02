import frappe
from frappe.desk.doctype.notification_settings.notification_settings import (
    NotificationSettings,
)

from real_group_hrms.overrides.user import has_itadmin_role


class NotificationSettingsOverride(NotificationSettings):
    pass


def has_permission(doc, ptype="read", user=None, debug=False):
    user = user or frappe.session.user

    if ptype in ("read", "write") and has_itadmin_role(user):
        return doc.name != "Administrator"


def toggle_notifications(user: str, enable: bool = False):
    try:
        settings = frappe.get_doc("Notification Settings", user)
    except frappe.DoesNotExistError:
        frappe.clear_last_message()
        return

    if settings.enabled != enable:
        settings.enabled = enable
        settings.save(ignore_permissions=has_itadmin_role())
