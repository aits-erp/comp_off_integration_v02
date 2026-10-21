# Copyright (c) 2024, Step Tech and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class EmployeeOnboardingForm(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from erpnext.setup.doctype.employee_education.employee_education import EmployeeEducation
        from erpnext.setup.doctype.employee_external_work_history.employee_external_work_history import (
            EmployeeExternalWorkHistory,
        )
        from frappe.types import DF

        from real_group_hrms.real_group.doctype.employee_family_details.employee_family_details import EmployeeFamilyDetails
        from real_group_hrms.real_group.doctype.employee_nominee.employee_nominee import EmployeeNominee

        aadhar_number: DF.Data
        addemergency_address: DF.SmallText | None
        addemergency_mobile: DF.Data | None
        addrelation: DF.Link | None
        bank_ac_no: DF.Data | None
        bank_name: DF.Data | None
        blood_group: DF.Literal["", "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
        cell_number: DF.Data | None
        current_accommodation_type: DF.Literal["", "Rented", "Owned"]
        current_address: DF.SmallText | None
        current_city: DF.Link
        current_country: DF.Link
        current_district: DF.Link
        current_pin_code: DF.Data | None
        current_state: DF.Link
        date_of_birth: DF.Date
        date_of_issue: DF.Data | None
        education: DF.Table[EmployeeEducation]
        emergency_address: DF.SmallText
        emergency_contact: DF.Data | None
        emergency_phone_number: DF.Data
        employee_name: DF.Data | None
        encryption_key: DF.Data | None
        external_work_history: DF.Table[EmployeeExternalWorkHistory]
        family_details: DF.Table[EmployeeFamilyDetails]
        father_name: DF.Data
        first_name: DF.Data
        gender: DF.Link
        health_details: DF.SmallText | None
        iban: DF.Data | None
        ifsc_code: DF.Data | None
        last_name: DF.Data | None
        marital_status: DF.Literal["", "Single", "Married", "Divorced", "Widowed"]
        micr_code: DF.Data | None
        middle_name: DF.Data | None
        mother_name: DF.Data
        nominee: DF.Table[EmployeeNominee]
        pan_number: DF.Data | None
        passport_number: DF.Data | None
        permanent_accommodation_type: DF.Literal["", "Rented", "Owned"]
        permanent_address: DF.SmallText | None
        permanent_city: DF.Link
        permanent_country: DF.Link
        permanent_district: DF.Link
        permanent_pin_code: DF.Data | None
        permanent_state: DF.Link
        person_to_be_contacted: DF.Data
        personal_email: DF.Data | None
        place_of_issue: DF.Data | None
        provident_fund_account: DF.Data | None
        relation: DF.Link | None
        religion: DF.Link
        salutation: DF.Link | None
        valid_upto: DF.Data | None
    # end: auto-generated types
    pass
