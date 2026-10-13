// Copyright (c) 2025, rtCamp and contributors
// For license information, please see license.txt

frappe.ui.form.on("bioattendancelog", {
  refresh(frm) {
    frm.disable_save();
    frm.save = () => {
      const message = __("Saving is disabled for bioattendancelog.");
      frappe.msgprint(message);
      return Promise.reject(new Error(message));
    };
  },
});
