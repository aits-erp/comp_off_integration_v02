# Copyright (c) 2024, Step Tech and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class RealGroupSettings(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF
        from real_group_hrms.real_group.doctype.oracle_credentials.oracle_credentials import OracleCredentials

        birthday_wish_message: DF.HTMLEditor | None
        birthday_wish_subject: DF.Data | None
        component_for_incentive: DF.Link | None
        email_account: DF.Link | None
        esic_deduction_limit: DF.Float
        oracle_credentials_details: DF.Table[OracleCredentials]
        pf_basic_limit: DF.Int
        time_pro_database: DF.Data | None
        time_pro_host: DF.Data | None
        time_pro_last_sync_on: DF.Datetime | None
        time_pro_password: DF.Password | None
        time_pro_port: DF.Data | None
        time_pro_user: DF.Data | None
    # end: auto-generated types
    pass
