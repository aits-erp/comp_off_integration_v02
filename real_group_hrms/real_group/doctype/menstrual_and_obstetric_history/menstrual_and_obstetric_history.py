# Copyright (c) 2024, Step Tech and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class MenstrualandObstetricHistory(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        date: DF.Date | None
        is_random_check: DF.Check
        medical_code: DF.Data | None
        medical_parameters: DF.Link
        parent: DF.Data
        parentfield: DF.Data
        parenttype: DF.Data
        uom: DF.Data | None
        value: DF.Float
    # end: auto-generated types
    pass
