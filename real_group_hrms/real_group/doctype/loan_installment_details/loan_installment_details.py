# Copyright (c) 2024, Step Tech and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class LoanInstallmentDetails(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        additional_salary: DF.Data
        amount: DF.Currency
        installment_date: DF.Date
        parent: DF.Data
        parentfield: DF.Data
        parenttype: DF.Data
        skip: DF.Check
    # end: auto-generated types
    pass
