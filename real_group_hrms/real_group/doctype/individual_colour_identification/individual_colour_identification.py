# Copyright (c) 2024, Step Tech and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class IndividualColourIdentification(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        left: DF.Data | None
        medical_parameters: DF.Link
        parent: DF.Data
        parentfield: DF.Data
        parenttype: DF.Data
        right: DF.Data | None
    # end: auto-generated types
    pass
