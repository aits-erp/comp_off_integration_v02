frappe.ui.form.on("Salary Structure", {
  refresh(frm) {
    if (frm.doc.earnings) {
      cur_frm.fields_dict["earnings"].grid.wrapper.find(".sortable-handle").css("pointer-events", "none");
      cur_frm.get_field("earnings").grid.cannot_add_rows = true;
    }
    if (frm.doc.deductions) {
      cur_frm.fields_dict["deductions"].grid.wrapper.find(".sortable-handle").css("pointer-events", "none");
      cur_frm.get_field("deductions").grid.cannot_add_rows = true;
    }
    frm.add_custom_button("Get Components From ERP", function () {
      let d = new frappe.ui.Dialog({
        title: "Salary Components Fetch from ERP",
        fields: [
          {
            label: "Company",
            fieldname: "company",
            fieldtype: "Link",
            options: "Company",
            reqd: 1,
          },
          {
            label: "Employee Category",
            fieldname: "employee_category",
            fieldtype: "Link",
            options: "Employee Category",
            reqd: 1,
          },
        ],
        size: "small", // small, large, extra-large
        primary_action_label: "Fetch Details",
        primary_action(values) {
          frappe.call({
            method: "real_group_hrms.real_group.integration.erp_config_master",
            args: {
              emp_catg: values.employee_category,
              company: values.company,
            },
            freeze: true,
            freeze_message: "Please Wait fetching all Earning & Deduction",
            callback: function (r) {
              if (!r.exc) {
                var jsonString = r.message;
                jsonString = jsonString ? jsonString : "[]";
                var resultList = JSON.parse(jsonString);

                if (resultList.length == 0) {
                  d.hide();
                  frappe.msgprint("Salary Components does not exist in ERP");
                } else {
                  resultList.forEach((rec) => {
                    if (rec.AFNO.includes("D")) {
                      var deductions_row = cur_frm.fields_dict.deductions.grid.add_new_row();
                      frappe.model.set_value(
                        deductions_row.doctype,
                        deductions_row.name,
                        "salary_component",
                        rec.salary_component
                      );
                      frappe.model.set_value(deductions_row.doctype, deductions_row.name, "abbr", rec.abbr);
                      frappe.model.set_value(
                        deductions_row.doctype,
                        deductions_row.name,
                        "custom_erp_rate",
                        rec.AFRATE
                      );
                      frappe.model.set_value(
                        deductions_row.doctype,
                        deductions_row.name,
                        "custom_erp_rate_indicator",
                        rec.AFRATEI
                      );
                    } else {
                      var earnings_row = cur_frm.fields_dict.earnings.grid.add_new_row();
                      frappe.model.set_value(
                        earnings_row.doctype,
                        earnings_row.name,
                        "salary_component",
                        rec.salary_component
                      );
                      frappe.model.set_value(earnings_row.doctype, earnings_row.name, "abbr", rec.abbr);
                      frappe.model.set_value(earnings_row.doctype, earnings_row.name, "custom_erp_rate", rec.AFRATE);
                      frappe.model.set_value(
                        earnings_row.doctype,
                        earnings_row.name,
                        "custom_erp_rate_indicator",
                        rec.AFRATEI
                      );
                    }

                    cur_frm.fields_dict["earnings"].grid.wrapper.find(".sortable-handle").css("pointer-events", "none");
                    cur_frm.get_field("earnings").grid.cannot_add_rows = true;
                    cur_frm.fields_dict["deductions"].grid.wrapper
                      .find(".sortable-handle")
                      .css("pointer-events", "none");
                    cur_frm.get_field("deductions").grid.cannot_add_rows = true;
                  });
                  d.hide();
                }
              } else {
                frappe.msgprint("Something went wrong, check logs");
              }
            },
          });
        },
      });

      d.show();
    });
  },
});
