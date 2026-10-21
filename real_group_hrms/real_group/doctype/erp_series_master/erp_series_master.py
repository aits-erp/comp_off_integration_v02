# Copyright (c) 2024, Step Tech and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class ERPSeriesMaster(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        branch: DF.Link | None
        company: DF.Link
        company_erp_code: DF.Data | None
        document_type: DF.Link
        erp_table_name: DF.Data
        formatter: DF.Literal["", "YYY", "YYM"]
        series_prefix: DF.Data
        tcode: DF.Data
    # end: auto-generated types
    pass
