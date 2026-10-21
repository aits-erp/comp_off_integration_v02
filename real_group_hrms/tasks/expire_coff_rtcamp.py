import frappe
from frappe.utils import flt, today


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


def expire_unused_comp_off():
    today_date = today()

    requests = frappe.get_all(
        "Compensatory Leave Request",
        filters={
            "expiry": today_date,
            "status": ["!=", "Expired"],
        },
        fields=["name", "employee", "credit", "leave_allocation"],
    )

    for req in requests:
        employee = req.employee
        credit = req.credit or 0

        if credit <= 0:
            frappe.db.set_value(
                "Compensatory Leave Request",
                req.name,
                "status",
                "Expired",
            )
            continue

        balance = frappe.db.sql(
            """
            SELECT IFNULL(SUM(leaves), 0)
            FROM `tabLeave Ledger Entry`
            WHERE employee=%s
              AND leave_type='Compensatory Off'
              AND docstatus=1
            """,
            employee,
        )[0][0]

        if balance <= 0:
            frappe.db.set_value(
                "Compensatory Leave Request",
                req.name,
                "status",
                "Expired",
            )
            continue

        expire_qty = min(balance, credit)

        transaction_type = "Compensatory Leave Request"
        transaction_name = req.name
        if req.get("leave_allocation"):
            transaction_type = "Leave Allocation"
            transaction_name = req.leave_allocation

        # Idempotency guard
        exists = frappe.db.exists(
            "Leave Ledger Entry",
            {
                "employee": employee,
                "leave_type": "Compensatory Off",
                "is_expired": 1,
                "transaction_type": transaction_type,
                "transaction_name": transaction_name,
                "from_date": today_date,
                "to_date": today_date,
                "docstatus": 1,
            },
        )
        if exists:
            frappe.db.set_value(
                "Compensatory Leave Request",
                req.name,
                "status",
                "Expired",
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
            date=today_date,
            transaction_type=transaction_type,
            transaction_name=transaction_name,
        )

        if transaction_type == "Leave Allocation" and transaction_name:
            allocation = frappe.db.get_value(
                "Leave Allocation",
                transaction_name,
                ["new_leaves_allocated", "total_leaves_allocated"],
                as_dict=True,
            )
            if allocation:
                frappe.db.set_value(
                    "Leave Allocation",
                    transaction_name,
                    "new_leaves_allocated",
                    max(0, flt(allocation.new_leaves_allocated) - flt(expire_qty)),
                )
                frappe.db.set_value(
                    "Leave Allocation",
                    transaction_name,
                    "total_leaves_allocated",
                    max(0, flt(allocation.total_leaves_allocated) - flt(expire_qty)),
                )

        frappe.db.set_value(
            "Compensatory Leave Request",
            req.name,
            "status",
            "Expired",
        )

    frappe.db.commit()
