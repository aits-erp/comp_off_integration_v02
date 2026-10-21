frappe.ui.form.on("Employee Onboarding Form", {
  refresh: function (frm) {
    frm.add_custom_button("Create Employee", function () {
      let employee = frappe.model.get_new_doc("Employee");

      employee.first_name = frm.doc.first_name;
      employee.middle_name = frm.doc.middle_name;
      employee.last_name = frm.doc.last_name;
      employee.employee_name = frm.doc.employee_name;
      employee.gender = frm.doc.gender;
      employee.date_of_birth = frm.doc.date_of_birth;
      employee.salutation = frm.doc.salutation;
      employee.date_of_joining = frm.doc.date_of_joining;
      employee.scheduled_confirmation_date = frm.doc.scheduled_confirmation_date;
      employee.final_confirmation_date = frm.doc.final_confirmation_date;
      employee.notice_number_of_days = frm.doc.notice_number_of_days;
      employee.cell_number = frm.doc.cell_number;
      employee.personal_email = frm.doc.personal_email;
      employee.prefered_email = frm.doc.prefered_email;
      employee.preferred_contact_email = frm.doc.preferred_contact_email;
      employee.permanent_address = frm.doc.permanent_address;
      employee.permanent_accommodation_type = frm.doc.permanent_accommodation_type;
      employee.custom_permanent_district = frm.doc.permanent_district;
      employee.custom_permanent_city = frm.doc.permanent_city;
      employee.custom_permanent_state = frm.doc.permanent_state;
      employee.custom_permanent_country = frm.doc.permanent_country;
      employee.custom_permanent_pin_code = frm.doc.permanent_pin_code;
      employee.current_address = frm.doc.current_address;
      employee.current_accommodation_type = frm.doc.current_accommodation_type;
      employee.custom_current_district = frm.doc.current_district;
      employee.custom_current_city = frm.doc.current_city;
      employee.custom_current_state = frm.doc.current_state;
      employee.custom_current_country = frm.doc.current_country;
      employee.custom_current_pin_code = frm.doc.current_pin_code;
      employee.person_to_be_contacted = frm.doc.person_to_be_contacted;
      employee.custom_emergency_address = frm.doc.emergency_address;
      employee.emergency_phone_number = frm.doc.emergency_phone_number;
      employee.relation = frm.doc.relation;
      employee.custom_additional_emegency_contact = frm.doc.emergency_contact;
      employee.custom_additional_emergency_address = frm.doc.addemergency_address;
      employee.custom_additional_emegency_mobile = frm.doc.addemergency_mobile;
      employee.custom_additional_relation = frm.doc.addrelation;
      employee.pan_number = frm.doc.pan_number;
      employee.provident_fund_account = frm.doc.provident_fund_account;
      employee.bank_name = frm.doc.bank_name;
      employee.bank_ac_no = frm.doc.bank_ac_no;
      employee.iban = frm.doc.iban;
      employee.ifsc_code = frm.doc.ifsc_code;
      employee.micr_code = frm.doc.micr_code;
      employee.blood_group = frm.doc.blood_group;
      employee.marital_status = frm.doc.marital_status;
      employee.custom_father_name = frm.doc.father_name;
      employee.custom_mother_name = frm.doc.mother_name;
      employee.custom_religion = frm.doc.religion;
      employee.custom_aadhar_number = frm.doc.aadhar_number;
      employee.health_details = frm.doc.health_details;
      employee.custom_skill_status = frm.doc.skill_status;
      employee.health_insurance_provider = frm.doc.health_insurance_provider;
      employee.passport_number = frm.doc.passport_number;
      employee.valid_upto = frm.doc.valid_upto;
      employee.date_of_issue = frm.doc.date_of_issue;
      employee.place_of_issue = frm.doc.place_of_issue;
      employee.bio = frm.doc.bio;

      frm.doc.family_details.forEach(function (d) {
        let child = frappe.model.add_child(employee, "Family Details", "custom_f_details");
        child.name1 = d.name1;
        child.occupation = d.occupation;
        child.relation = d.relation;
        child.blood_group = d.blood_group;
      });

      frm.doc.education.forEach(function (d) {
        let child = frappe.model.add_child(employee, "Education", "education");
        child.school_univ = d.school_univ;
        child.qualification = d.qualification;
        child.level = d.level;
        child.year_of_passing = d.year_of_passing;
        child.class_per = d.class_per;
        child.maj_opt_subj = d.maj_opt_subj;
      });

      frm.doc.external_work_history.forEach(function (d) {
        let child = frappe.model.add_child(employee, "External Work History", "external_work_history");
        child.designation = d.designation;
        child.salary = d.salary;
        child.address = d.address;
        child.contact = d.contact;
        child.total_experience = d.total_experience;
      });

      frm.doc.nominee.forEach(function (d) {
        let child = frappe.model.add_child(employee, "Employee Nominee", "custom_nominee");
        child.nominee_name = d.nominee_name;
        child.allocation_percentage = d.allocation_percentage;
        child.relation = d.relation;
      });

      frappe.set_route("form", "Employee", employee.name);
    });
  },
});
