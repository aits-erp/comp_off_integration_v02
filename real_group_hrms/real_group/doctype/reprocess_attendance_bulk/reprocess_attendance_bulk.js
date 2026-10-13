// Copyright (c) 2024, Step Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Reprocess Attendance Bulk", {
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
