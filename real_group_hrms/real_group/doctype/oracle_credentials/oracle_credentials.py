# Copyright (c) 2024, Step Tech and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class OracleCredentials(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        company: DF.Link
        company_abbr: DF.Data | None
        database: DF.Data
        host: DF.Data
        parent: DF.Data
        parentfield: DF.Data
        parenttype: DF.Data
        password: DF.Password
        username: DF.Data
    # end: auto-generated types
    pass
