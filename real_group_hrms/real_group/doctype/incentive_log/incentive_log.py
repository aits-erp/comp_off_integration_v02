# Copyright (c) 2024, Step Tech and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class IncentiveLog(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        amended_from: DF.Link | None
        credit: DF.Float
        employee: DF.Link | None
        employee_name: DF.Data | None
        extra_incentive: DF.Float
        extra_worked_hours: DF.Time | None
        from_date: DF.Date | None
        incentive: DF.Float
        incentive_original_value: DF.Float
        status: DF.Data | None
        to_date: DF.Date | None
        total_incentive: DF.Float
        work_date: DF.Date | None
    # end: auto-generated types
    pass
