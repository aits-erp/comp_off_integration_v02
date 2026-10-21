# Copyright (c) 2024, Step Tech and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class EmployeeFamilyDetails(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        blood_group: DF.Literal["", "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
        name1: DF.Data | None
        occupation: DF.Link | None
        parent: DF.Data
        parentfield: DF.Data
        parenttype: DF.Data
        relation: DF.Link | None
    # end: auto-generated types
    pass
