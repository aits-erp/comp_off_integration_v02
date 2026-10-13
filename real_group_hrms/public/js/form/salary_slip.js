frappe.ui.form.on("Salary Slip", {
  refresh(frm) {
    if (frm.doc.docstatus == 1) {
      frm.add_custom_button("Email Salary Slip", function () {
        frappe
          .call("mail_salary_slip", {
            salary_slip: frm.doc.name,
          })
          .then((x) => {
            console.log(x);
          });
      });
    }
  },
});
