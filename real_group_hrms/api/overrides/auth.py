import frappe
from frappe import _
from frappe.utils import (
    get_url,
)


@frappe.whitelist(allow_guest=True)
def send_login_link(email: str):
    if not frappe.get_system_settings("login_with_email_link"):
        return

    expiry = frappe.get_system_settings("login_with_email_link_expiry") or 10
    link = _generate_temporary_login_link(email, expiry)

    app_name = frappe.get_website_settings("app_name") or frappe.get_system_settings("app_name") or _("Frappe")

    subject = _("Login To {0}").format(app_name)

    email = frappe.db.get_value("User", email, "email")

    frappe.sendmail(
        subject=subject,
        recipients=email,
        template="login_with_email_link",
        args={"link": link, "minutes": expiry, "app_name": app_name},
        now=True,
    )


def _generate_temporary_login_link(email: str, expiry: int):
    assert isinstance(email, str)

    if not frappe.db.exists("User", email):
        frappe.throw(_("User with email address {0} does not exist").format(email), frappe.DoesNotExistError)
    key = frappe.generate_hash()
    frappe.cache.set_value(f"one_time_login_key:{key}", email, expires_in_sec=expiry * 60)

    return get_url(f"/api/method/frappe.www.login.login_via_key?key={key}")
