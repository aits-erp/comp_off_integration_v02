# Copyright (c) 2026, rtCamp and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class BonusSlip(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        amended_from: DF.Link | None
        bonus_amount: DF.Currency
        bonus_percentage: DF.Float
        branch: DF.Link
        company: DF.Link
        currency: DF.Link
        division: DF.Link
        employee: DF.Link
        employee_name: DF.Data | None
        erp_bonus_payment_vrno: DF.Data | None
        erp_bonus_sync: DF.Check
        erp_bonus_vrno: DF.Data | None
        posting_date: DF.Date
        retention_bonus: DF.Link | None
        salary_slip: DF.Link
    # end: auto-generated types
    pass
