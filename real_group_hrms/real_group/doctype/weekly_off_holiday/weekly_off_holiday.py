# Copyright (c) 2025, rtCamp and contributors
# For license information, please see license.txt


from frappe.model.document import Document


class WeeklyOffHoliday(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        description: DF.TextEditor
        holiday_date: DF.Date
        parent: DF.Data
        parentfield: DF.Data
        parenttype: DF.Data
    # end: auto-generated types
    pass
