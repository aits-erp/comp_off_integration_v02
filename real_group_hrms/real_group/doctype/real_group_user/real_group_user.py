# Copyright (c) 2024, Step Tech and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class RealGroupUser(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        accounting_year: DF.Link | None
        birth_date: DF.Date | None
        company: DF.Link | None
        department: DF.Link | None
        email: DF.Data | None
        enable: DF.Check
        first_name: DF.Data
        full_name: DF.Data
        gender: DF.Link | None
        language: DF.Link | None
        last_name: DF.Data | None
        location: DF.Data | None
        middle_name: DF.Data | None
        mobile: DF.Data | None
        password_reset_days: DF.Int
        password_type: DF.Data | None
        phone: DF.Data | None
        user: DF.Link | None
        username: DF.Data | None
    # end: auto-generated types
    pass
