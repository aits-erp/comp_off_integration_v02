# Copyright (c) 2024, Step Tech and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class EmergencyContacts(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        emergency_contact_name: DF.Data | None
        emergency_phone: DF.Float
        parent: DF.Data
        parentfield: DF.Data
        parenttype: DF.Data
        relation: DF.Literal["Father", "Mother", "Brother", "Sister", "Wife", "Husband", "Son", "Daughter", "Other"]
    # end: auto-generated types
    pass
