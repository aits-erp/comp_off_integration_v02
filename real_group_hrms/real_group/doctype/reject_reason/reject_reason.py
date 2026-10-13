# Copyright (c) 2024, Step Tech and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class RejectReason(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        from real_group_hrms.real_group.doctype.reject_reason_type.reject_reason_type import RejectReasonType

        document_type: DF.TableMultiSelect[RejectReasonType]
        reason: DF.Data | None
    # end: auto-generated types
    pass
