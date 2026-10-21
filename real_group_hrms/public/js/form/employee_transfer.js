frappe.ui.form.on("Employee Transfer", {
  refresh: function (frm) {
    frm.fields_dict.custom_employee_leave.grid.grid_buttons.hide();
  },
  employee: function (frm) {
    if (frm.doc.employee) {
      frm.trigger("reallocate_leaves");
    }
  },
  reallocate_leaves: function (frm) {
    if (frm.doc.reallocate_leaves) {
      frm.trigger("get_leave_info");
    }
  },
  validate: function (frm) {
    if (frm.doc.custom_employee_leave) {
      frm.doc.custom_employee_leave.forEach(function (d) {
        if (!d.expire) {
          if (!d.number_of_leaves) {
            frappe.validated = false;
            frappe.msgprint({
              title: __("Missing Value"),
              message: __("Number of Leaves is required in row {0} of Employee Leave Transfer table.", [d.idx]),
              indicator: "red",
            });
          }
          if (!d.new_leave_type) {
            frappe.validated = false;
            frappe.msgprint({
              title: __("Missing Value"),
              message: __("New Leave Type is required in row {0} of Employee Leave Transfer table.", [d.idx]),
              indicator: "red",
            });
          }
        }
      });
    }
  },
  get_leave_info: function (frm) {
    if (!frm.doc.employee) {
      frappe.throw(__("Please select an Employee first."));
    }

    frappe.call({
      method: "real_group_hrms.api.employee_transfer.get_leave_details",
      args: { employee: frm.doc.employee, date: frappe.datetime.get_today() },
      callback: function (r) {
        if (r.message) {
          const data = r.message.leave_allocation;
          frm.clear_table("custom_employee_leave");
          $.each(data, function (i, d) {
            var child = frm.add_child("custom_employee_leave", {
              existing_leave_type: i,
              number_of_leaves: d.remaining_leaves,
            });
            frm.fields_dict.custom_employee_leave.grid.toggle_enable("existing_leave_type", false);
          });
          frm.refresh_field("custom_employee_leave");
          frm.fields_dict.custom_employee_leave.grid.grid_buttons.hide();
        }
      },
    });
  },
});
