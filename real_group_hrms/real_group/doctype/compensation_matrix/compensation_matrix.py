# Copyright (c) 2024, Step Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import get_time


class CompensationMatrix(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        from real_group_hrms.real_group.doctype.compensation_matrix_details.compensation_matrix_details import (
            CompensationMatrixDetails,
        )

        branch: DF.Link
        description: DF.Data
        items: DF.Table[CompensationMatrixDetails]
        shift_duration: DF.Time

    # end: auto-generated types
    def before_save(self):
        self.validate_from_and_to_time()

    def validate_from_and_to_time(self):
        for i in self.items:
            if i.c_off_credit % 1 != 0.5 and i.c_off_credit % 1 != 0:
                frappe.throw(frappe._("Value for C Off Credit must end in .0 or .5"))
            if get_time(i.from_hrs) > get_time(i.to_hrs):
                frappe.throw(
                    frappe._("Extra Hours Start must be less than Extra hours end {0} and {1}").format(
                        i.from_hrs, i.to_hrs
                    )
                )
