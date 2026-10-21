// Copyright (c) 2024, Step Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Reprocess Attendance", {
  employee: function (frm) {
    frappe.db.get_value("Employee", frm.doc.employee, ["company", "branch"]).then((r) => {
      const data = r.message;
      frm.set_value("company", data.company);
      frm.set_value("branch", data.branch);
    });
  },
  validate(frm) {
    frm.trigger("validateDate");
  },
  to_date(frm) {
    frm.trigger("validateDate");
  },
  validateDate(frm) {
    const dayDiff = frappe.datetime.get_day_diff(frappe.datetime.get_today(), frm.doc.to_date);
    if (dayDiff < 1) {
      frappe.msgprint(__("To Date must be at least 1 day before today's date"));
      frappe.validated = false;
    }
  },
});
