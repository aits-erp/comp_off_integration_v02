# Copyright (c) 2025, rtCamp and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import add_days, get_datetime, getdate


class GatePass(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        amended_from: DF.Link | None
        branch: DF.Link | None
        checkout_time: DF.Datetime | None
        company: DF.Link | None
        date: DF.Date
        department: DF.Link | None
        division: DF.Link | None
        employee: DF.Link
        employee_name: DF.Data | None
        name: DF.Int | None
        reason: DF.Literal["", "Personal", "Official"]
        reason_detail: DF.SmallText
        status: DF.Literal["Draft", "Pending", "Rejected", "Approved"]
    # end: auto-generated types
    def validate(self):
        self.validate_total_gate_pass_per_day()
        self.validate_checkout_before_approval()

    def before_insert(self):
        self.validate_date()
        self.validate_checkin()
        self.validate_branch()

    def validate_total_gate_pass_per_day(self):
        if not self.employee or not self.date:
            return

        in_log_count = get_in_log_count(self.employee, self.date)
        if in_log_count <= 0:
            frappe.throw(frappe._("Employee has not checked in today. Cannot create Gate Pass."))

        existing_gate_passes = frappe.get_all(
            "Gate Pass",
            filters=[
                ["employee", "=", self.employee],
                ["date", "=", self.date],
                ["docstatus", "in", [0, 1]],
                ["status", "!=", "Rejected"],
                ["name", "!=", self.name or ""],
            ],
            pluck="name",
        )

        if len(existing_gate_passes) >= in_log_count:
            frappe.throw(
                frappe._("You can create at most {0} Gate Pass(es) for this date based on your check-ins.").format(
                    in_log_count
                ),
                title=frappe._("Gate Pass Limit Reached"),
            )

    def validate_date(self):
        if getdate(self.date) < getdate():
            frappe.throw(frappe._("Gate Pass date cannot be created for past dates"))
        if getdate(self.date) > getdate():
            frappe.throw(frappe._("Gate Pass date cannot be created for future dates"))

    def validate_checkin(self):
        in_log_count = get_in_log_count(self.employee, self.date)
        if in_log_count <= 0:
            frappe.throw(frappe._("Employee has not checked in today. Cannot create Gate Pass."))

    def validate_branch(self):
        branch = frappe.db.get_value("Employee", self.employee, "branch")
        if not branch:
            return
        skip_gate_pass = frappe.db.get_value("Branch", branch, "custom_skip_gate_pass")
        if skip_gate_pass == 1:
            frappe.throw(frappe._("Branch doesn't allow gate pass."))

    def validate_checkout_before_approval(self):
        is_approved_state = False
        if self.meta.has_field("workflow_state"):
            is_approved_state = self.workflow_state == "Approved"
        else:
            is_approved_state = self.status == "Approved"

        if not is_approved_state or not self.employee or not self.date:
            return

        latest_checkout = get_latest_checkout_time(self.employee, str(self.date))
        if not latest_checkout:
            frappe.throw(
                frappe._(
                    "Employee's latest log for this date must be Check Out. Gate Pass cannot be approved before final checkout."
                )
            )

        self.checkout_time = latest_checkout


def get_in_log_count(employee: str, date: str) -> int:
    if not employee or not date:
        return 0

    start_time = get_datetime(date)
    end_time = get_datetime(add_days(getdate(date), 1))
    in_logs = frappe.get_all(
        "Employee Checkin",
        filters=[
            ["employee", "=", employee],
            ["log_type", "=", "IN"],
            ["time", ">=", start_time],
            ["time", "<", end_time],
        ],
        pluck="name",
    )
    return len(in_logs)


def get_existing_gate_pass_count(employee: str, date: str, exclude_name: str | None = None) -> int:
    if not employee or not date:
        return 0

    filters = [
        ["employee", "=", employee],
        ["date", "=", date],
        ["docstatus", "in", [0, 1]],
        ["status", "!=", "Rejected"],
    ]
    if exclude_name:
        filters.append(["name", "!=", exclude_name])

    return len(frappe.get_all("Gate Pass", filters=filters, pluck="name"))


def get_team_gate_pass_visible_states(user: str | None = None) -> list[str]:
    user = user or frappe.session.user
    roles = set(frappe.get_roles(user))
    visible_states = set()

    if "Leave Approver" in roles:
        visible_states.update({"Pending at HOD", "Rejected by HOD"})

    if "Gate-RA" in roles:
        visible_states.update({"Gate Pass", "Approved", "Rejected at Gate"})

    return sorted(visible_states)


def get_team_gate_pass_allowed_employees(user: str | None = None) -> list[str]:
    user = user or frappe.session.user

    allowed_employees = frappe.get_all(
        "User Permission",
        filters=[
            ["user", "=", user],
            ["allow", "=", "Employee"],
            ["for_value", "!=", ""],
            ["applicable_for", "in", ["Gate Pass", "", None]],
        ],
        pluck="for_value",
    )

    return sorted(set(allowed_employees))


def expire_gate_passes():
    gate_passes = frappe.get_all(
        "Gate Pass",
        filters={"docstatus": 0, "date": ("<", getdate())},
        pluck="name",
    )
    for gate_pass in gate_passes:
        doc = frappe.get_doc("Gate Pass", gate_pass)
        doc.status = "Rejected"
        if doc.meta.has_field("workflow_state") and doc.workflow_state == "Gate Pass":
            doc.workflow_state = "Rejected at Gate"
        doc.submit()


@frappe.whitelist()
def get_latest_checkout_time(employee: str, date: str):
    if not employee or not date:
        return None

    gate_pass_date = getdate(date)
    start_time = get_datetime(gate_pass_date)
    end_time = get_datetime(add_days(gate_pass_date, 1))

    latest_log = frappe.get_list(
        "Employee Checkin",
        filters=[
            ["employee", "=", employee],
            ["time", ">=", start_time],
            ["time", "<", end_time],
        ],
        fields=["time", "log_type"],
        order_by="time desc",
        limit=1,
    )

    if not latest_log:
        return None

    latest_log = latest_log[0]
    if latest_log.get("log_type") != "OUT":
        return None

    return latest_log.get("time")


@frappe.whitelist()
def get_gate_pass_eligibility(employee: str, date: str, docname: str | None = None):
    response = {
        "allowed": False,
        "message": "",
        "in_log_count": 0,
        "existing_gate_pass_count": 0,
        "remaining_gate_pass_count": 0,
        "custom_skip_gate_pass": 0,
    }

    if not employee:
        response["message"] = frappe._("Employee is required.")
        return response

    if not date:
        response["message"] = frappe._("Date is required.")
        return response

    target_date = getdate(date)
    if target_date < getdate():
        response["message"] = frappe._("Gate Pass date cannot be created for past dates")
        return response
    if target_date > getdate():
        response["message"] = frappe._("Gate Pass date cannot be created for future dates")
        return response

    branch = frappe.db.get_value("Employee", employee, "branch")
    if branch:
        response["custom_skip_gate_pass"] = frappe.db.get_value("Branch", branch, "custom_skip_gate_pass") or 0
        if response["custom_skip_gate_pass"]:
            response["message"] = frappe._("Branch doesn't allow gate pass.")
            return response

    in_log_count = get_in_log_count(employee, target_date)
    response["in_log_count"] = in_log_count
    if in_log_count <= 0:
        response["message"] = frappe._("Employee has not checked in today. Cannot create Gate Pass.")
        return response

    existing_gate_pass_count = get_existing_gate_pass_count(employee, target_date, docname)
    response["existing_gate_pass_count"] = existing_gate_pass_count
    response["remaining_gate_pass_count"] = max(in_log_count - existing_gate_pass_count, 0)

    if existing_gate_pass_count >= in_log_count:
        response["message"] = frappe._(
            "You can create at most {0} Gate Pass(es) for this date based on your check-ins."
        ).format(in_log_count)
        return response

    response["allowed"] = True
    return response


@frappe.whitelist()
def get_pwa_team_gate_pass_list(status: str | None = None, date: str | None = None, start: int = 0, page_length: int = 50):
    start = int(start or 0)
    page_length = int(page_length or 50)

    visible_states = set(get_team_gate_pass_visible_states())
    if not visible_states:
        return []

    allowed_employees = set(get_team_gate_pass_allowed_employees())
    if not allowed_employees:
        return []

    employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    if employee:
        allowed_employees.discard(employee)
    if not allowed_employees:
        return []

    grouped_states = {
        "Open": {"Pending at HOD", "Gate Pass"},
        "Approved": {"Approved"},
        "Rejected": {"Rejected by HOD", "Rejected at Gate"},
    }
    if status:
        visible_states &= grouped_states.get(status, set())
        if not visible_states:
            return []

    filters = [
        ["docstatus", "!=", 2],
        ["workflow_state", "in", sorted(visible_states)],
        ["employee", "in", sorted(allowed_employees)],
    ]
    if date:
        filters.append(["date", "=", getdate(date)])

    return frappe.get_list(
        "Gate Pass",
        filters=filters,
        fields=[
            "name",
            "employee",
            "employee_name",
            "date",
            "reason",
            "checkout_time",
            "status",
            "workflow_state",
            "modified",
        ],
        order_by="modified desc",
        start=start,
        page_length=page_length,
    )
