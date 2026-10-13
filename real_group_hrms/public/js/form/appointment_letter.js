frappe.ui.form.on("Appointment Letter", {
  refresh(frm) {
    frm.add_custom_button("Send Employee Onboarding Form", function () {
      frappe
        .call("create_employee_onboarding_form", {
          job_applicant: frm.doc.job_applicant,
          applicant_name: frm.doc.applicant_name,
        })
        .then((resp) => {
          if (!resp.exc) {
            frappe.msgprint("Employee Onboarding Message Sent");
          }
        });
    });
  },
});
