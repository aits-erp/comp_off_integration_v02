// Copyright (c) 2025, rtCamp and contributors
// For license information, please see license.txt

frappe.ui.form.on("Employee Series", {
  before_save(frm) {
    frm.trigger("validate");
  },
  validate(frm) {
    if (frm.doc.start >= frm.doc.end) {
      frappe.throw(__("Start Number cannot be greater than or equal to End Number"));
    }

    const filters = {
      company: frm.doc.company,
      is_active: 1,
    };
    if (frm.doc.name) {
      filters["name"] = ["!=", frm.doc.name];
    }
    frappe
      .call({
        method: "frappe.client.get_value",
        args: {
          doctype: "Employee Series",
          fieldname: "name",
          filters: filters,
        },
      })
      .then((response) => {
        if (response.message) {
          const name = response.message.name;
          if (!name) return;
          frappe.throw(
            `An active Employee Series already exists for this company: ${frappe.utils.get_form_link(
              "Employee Series",
              name,
              true
            )}. Please deactivate it before activating a new one.`
          );
        }
      });
  },
});
