# Copyright (c) 2024, Step Tech and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class MedicalParameters(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        common_parameter: DF.Check
        measure_code: DF.Data | None
        measure_name: DF.Data | None
        parameter_type: DF.Literal[
            "",
            "Random Check",
            "Complete Blood Count",
            "Differential Leucocyte Count",
            "Kidney Function Test",
            "Liver Function Test",
            "Lipid Profile Test",
            "Urine Physical Examination",
            "Urine Chemical Examination",
            "Urine Microscopic Examination",
            "Biochemistry",
            "Pulmonary Function Test",
            "General Examination",
            "Cardiovascular System",
            "Respiratory System",
            "Gastrointestinal System",
            "Examination Of Eyes",
            "Individual Color Identification",
            "Gastro Urinary System",
            "Audiometry Examination",
            "Menstrual and Obstetric History",
            "Scheduled Test",
            "Both",
        ]
        uom: DF.Link | None
    # end: auto-generated types
    pass
