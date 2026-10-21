frappe.ui.form.on("Additional Salary", {
  payroll_date(frm) {
    if (frm.doc.payroll_date) {
      frm.set_value("custom_month", moment.months()[Number(frm.doc.payroll_date.split("-")[1])]);
    }
  },
});
