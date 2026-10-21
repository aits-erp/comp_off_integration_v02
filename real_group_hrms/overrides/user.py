import frappe
from frappe import STANDARD_USERS, _
from frappe.core.doctype.user.user import User
from frappe.utils import cint, validate_email_address


def has_itadmin_role(user=None):
    user = user or frappe.session.user
    return any(role.startswith("ITAdmin") for role in frappe.get_roles(user))


class UserOverride(User):
    def autoname(self):
        """set name as Email Address"""
        if self.get("is_admin") or self.get("is_guest"):
            self.name = self.first_name
        else:
            self.email = self.email.strip().lower() if self.email else ""
            self.name = self.username

    def validate(self):
        # Preserve entered email before core validate sets email = name.
        requested_email = self._normalize_email(self.email)
        previous_email = self._normalize_email(self._get_previous_email())

        super().validate()

        target_email = requested_email
        if self.name not in ("Administrator", "Guest") and not cint(self.enabled):
            # Free up email on disable so it can be reused.
            target_email = None

        self._validate_email_lock(previous_email, target_email)
        self._validate_email_policy(target_email)
        self.email = target_email

    def validate_email_type(self, email):
        # No need to validate email, since it is not used.
        pass

    def check_enable_disable(self):
        if not cint(self.enabled) and self.name in STANDARD_USERS:
            frappe.throw(_("User {0} cannot be disabled").format(self.name))

        if not cint(self.enabled):
            self.a_system_manager_should_exist()

        if not cint(self.enabled) and getattr(frappe.local, "login_manager", None):
            frappe.local.login_manager.logout(user=self.name)

        from real_group_hrms.overrides.notification_settings import toggle_notifications

        toggle_notifications(self.name, enable=cint(self.enabled))

    def _validate_email_policy(self, target_email):
        if not target_email:
            return

        validate_email_address(target_email, True)

        if not cint(self.enabled):
            return

        existing_user = frappe.db.get_value(
            "User",
            {"name": ["!=", self.name], "enabled": 1, "email": target_email},
            "name",
        )
        if existing_user:
            frappe.throw(
                _("Email {0} is already linked with active user {1}.").format(target_email, existing_user)
            )

    def _validate_email_lock(self, previous_email, target_email):
        if not previous_email:
            return

        if previous_email == target_email:
            return

        if not cint(self.enabled) and not target_email:
            # Allow automatic clear while disabling user.
            return

        frappe.throw(_("Email can be set only once and cannot be changed."))

    def _get_previous_email(self):
        if self.is_new():
            return None

        return frappe.db.get_value("User", self.name, "email")

    @staticmethod
    def _normalize_email(value):
        if not value:
            return None

        value = value.strip().lower()
        return value or None
