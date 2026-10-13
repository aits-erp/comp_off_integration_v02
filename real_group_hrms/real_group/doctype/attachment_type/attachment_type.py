# Copyright (c) 2024, Step Tech and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class AttachmentType(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        allowed_formats: DF.Data | None
        attach: DF.Attach | None
        attachment_type: DF.Literal[
            "", "X Ray Film", "ECG", "Audiometry", "Spirometry", "Ultrasound Abdomen", "Form 21"
        ]
        parent: DF.Data
        parentfield: DF.Data
        parenttype: DF.Data
        remarks: DF.SmallText | None
    # end: auto-generated types
    pass
