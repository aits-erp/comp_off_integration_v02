# Copyright (c) 2024, Step Tech and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class CompensationLeaveLedger(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        actual_count: DF.Float
        branch: DF.Link | None
        company: DF.Link | None
        department: DF.Link | None
        division: DF.Link | None
        employee: DF.Link | None
        employee_name: DF.Data | None
        leave_count: DF.Float
        leave_expiry: DF.Date | None
        leave_from: DF.Date | None
        reference_no: DF.Data | None
        status: DF.Data | None
        work_date: DF.Date | None
    # end: auto-generated types
    pass
