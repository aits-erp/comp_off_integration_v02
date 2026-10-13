from datetime import timedelta

import frappe
from frappe.utils import flt, getdate, today


def get_total_comp_off_outflow(employee: str) -> float:
    """Total consumed/expired C-off leaves to distribute FIFO across requests."""

    outflow = frappe.db.sql(
        """
        SELECT IFNULL(SUM(-leaves), 0)
        FROM `tabLeave Ledger Entry`
        WHERE employee=%s
          AND leave_type='Compensatory Off'
          AND docstatus=1
          AND leaves < 0
          AND (
                transaction_type='Leave Application'
                OR (
                    transaction_type='Leave Allocation'
                    AND is_expired=1
                    AND is_carry_forward=0
                )
              )
        """,
        (employee,),
    )[0][0]
    return flt(outflow)


def get_fifo_request_balances(employee: str) -> dict[str, float]:
    """
    Compute request-wise remaining balance in FIFO order.

    This prevents an old, already consumed C-off request from expiring
    a newer request in the same leave allocation pool.
    """

    requests = frappe.get_all(
        "Compensatory Leave Request",
        filters={"employee": employee, "docstatus": 1},
        fields=["name", "credit", "work_end_date", "work_from_date", "creation"],
        order_by="work_end_date asc, work_from_date asc, creation asc",
    )

    outflow_remaining = get_total_comp_off_outflow(employee)
    request_balances: dict[str, float] = {}

    for req in requests:
        credit = flt(req.credit or 0)
        consumed = min(credit, outflow_remaining)
        request_balance = max(0.0, credit - consumed)
        request_balances[req.name] = request_balance
        outflow_remaining = max(0.0, outflow_remaining - consumed)

    return request_balances


def create_comp_off_expiry_ledger(
    employee,
    employee_name,
    company,
    expire_qty,
    date,
    transaction_type,
    transaction_name,
):
    doc = frappe.get_doc(
        {
            "doctype": "Leave Ledger Entry",
            "employee": employee,
            "employee_name": employee_name,
            "company": company,
            "leave_type": "Compensatory Off",
            "transaction_type": transaction_type,
            "transaction_name": transaction_name,
            "leaves": -expire_qty,
            "from_date": date,
            "to_date": date,
            "is_expired": 1,
            "is_carry_forward": 0,
            "is_lwp": 0,
        }
    )

    doc.flags.ignore_permissions = 1
    doc.flags.ignore_links = 1

    doc.insert()
    doc.submit()


def get_allocation_balance(employee: str, allocation_name: str) -> float:
    """Returns current remaining C-off balance for a specific Leave Allocation."""
    if not allocation_name:
        return 0.0

    balance = frappe.db.sql(
        """
        SELECT IFNULL(SUM(leaves), 0)
        FROM `tabLeave Ledger Entry`
        WHERE employee=%s
          AND leave_type='Compensatory Off'
          AND transaction_type='Leave Allocation'
          AND transaction_name=%s
          AND docstatus=1
        """,
        (employee, allocation_name),
    )[0][0]
    return flt(balance)


def mark_request_expired(
    request_name: str,
    has_custom_is_expired: bool = False,
    has_custom_expired_leaves: bool = False,
    has_custom_balance: bool = False,
    expired_qty: float = 0.0,
) -> None:
    frappe.db.set_value("Compensatory Leave Request", request_name, "status", "Expired")

    if has_custom_is_expired:
        frappe.db.set_value(
            "Compensatory Leave Request", request_name, "custom_is_expired", 1
        )

    if has_custom_expired_leaves and expired_qty > 0:
        existing_expired = flt(
            frappe.db.get_value(
                "Compensatory Leave Request", request_name, "custom_expired_leaves"
            )
            or 0
        )
        frappe.db.set_value(
            "Compensatory Leave Request",
            request_name,
            "custom_expired_leaves",
            existing_expired + flt(expired_qty),
        )

    if has_custom_balance:
        frappe.db.set_value(
            "Compensatory Leave Request", request_name, "custom_balance", 0
        )


def get_previous_month_end(as_of_date=None):
    run_date = getdate(as_of_date or today())
    return run_date.replace(day=1) - timedelta(days=1)


def expire_unused_comp_off(as_of_date=None):
    expiry_cutoff_date = get_previous_month_end(as_of_date)
    clr_meta = frappe.get_meta("Compensatory Leave Request")
    has_custom_balance = clr_meta.has_field("custom_balance")
    has_custom_is_expired = clr_meta.has_field("custom_is_expired")
    has_custom_expired_leaves = clr_meta.has_field("custom_expired_leaves")

    requests = frappe.get_all(
        "Compensatory Leave Request",
        filters={
            # Monthly expiry run: expire requests whose configured expiry date
            # is up to the last day of the previous month.
            "expiry": ["<=", expiry_cutoff_date],
            "docstatus": 1,
            "status": ["!=", "Expired"],
        },
        fields=[
            "name",
            "employee",
            "credit",
            "leave_allocation",
            "expiry",
            "work_end_date",
            "creation",
        ],
        order_by="employee asc, expiry asc, work_end_date asc, creation asc",
    )

    fifo_balances_by_employee: dict[str, dict[str, float]] = {}

    for req in requests:
        employee = req.employee

        if employee not in fifo_balances_by_employee:
            fifo_balances_by_employee[employee] = get_fifo_request_balances(employee)

        if has_custom_is_expired:
            is_already_expired = frappe.db.get_value(
                "Compensatory Leave Request", req.name, "custom_is_expired"
            )
            if is_already_expired:
                mark_request_expired(
                    req.name,
                    has_custom_is_expired=has_custom_is_expired,
                    has_custom_expired_leaves=has_custom_expired_leaves,
                    has_custom_balance=has_custom_balance,
                )
                continue

        # Use FIFO-derived per-request balance so old consumed requests
        # don't expire newer request balances.
        request_balance = flt(
            fifo_balances_by_employee.get(employee, {}).get(req.name, req.credit or 0)
        )

        if has_custom_balance:
            custom_balance = flt(
                frappe.db.get_value(
                    "Compensatory Leave Request", req.name, "custom_balance"
                )
                or 0
            )
            # Guard against stale custom balance defaults (0 on many sites).
            # Only use it when it carries a positive value.
            if custom_balance > 0:
                request_balance = min(request_balance, custom_balance)

        if request_balance <= 0:
            mark_request_expired(
                req.name,
                has_custom_is_expired=has_custom_is_expired,
                has_custom_expired_leaves=has_custom_expired_leaves,
                has_custom_balance=has_custom_balance,
            )
            continue

        if not req.leave_allocation:
            frappe.log_error(
                title="C-off Expiry Skipped (Missing Leave Allocation)",
                message=f"Compensatory Leave Request {req.name} has no leave_allocation; marking as expired.",
            )
            mark_request_expired(
                req.name,
                has_custom_is_expired=has_custom_is_expired,
                has_custom_expired_leaves=has_custom_expired_leaves,
                has_custom_balance=has_custom_balance,
            )
            continue

        allocation_balance = get_allocation_balance(employee, req.leave_allocation)
        if allocation_balance <= 0:
            mark_request_expired(
                req.name,
                has_custom_is_expired=has_custom_is_expired,
                has_custom_expired_leaves=has_custom_expired_leaves,
                has_custom_balance=has_custom_balance,
            )
            continue

        # Rule: expire only when available C-Off balance is enough to cover
        # this request's remaining expiry balance.
        if allocation_balance < request_balance:
            continue

        expire_qty = request_balance
        if expire_qty <= 0:
            mark_request_expired(
                req.name,
                has_custom_is_expired=has_custom_is_expired,
                has_custom_expired_leaves=has_custom_expired_leaves,
                has_custom_balance=has_custom_balance,
            )
            continue

        employee_doc = frappe.db.get_value(
            "Employee",
            employee,
            ["employee_name", "company"],
            as_dict=True,
        )

        create_comp_off_expiry_ledger(
            employee=employee,
            employee_name=employee_doc.employee_name,
            company=employee_doc.company,
            expire_qty=expire_qty,
            date=req.expiry,
            transaction_type="Leave Allocation",
            transaction_name=req.leave_allocation,
        )

        mark_request_expired(
            req.name,
            has_custom_is_expired=has_custom_is_expired,
            has_custom_expired_leaves=has_custom_expired_leaves,
            has_custom_balance=has_custom_balance,
            expired_qty=expire_qty,
        )

    frappe.db.commit()
