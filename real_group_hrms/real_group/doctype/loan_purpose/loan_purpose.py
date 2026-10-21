# Copyright (c) 2024, Step Tech and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class LoanPurpose(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        erp_code: DF.Data
        installment_amount: DF.Float
        loan_amount: DF.Float
        loan_purpose: DF.Data | None
        number_of_installments: DF.Int
    # end: auto-generated types
    pass
