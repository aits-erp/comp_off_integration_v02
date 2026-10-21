frappe.ui.form.on("Salary Structure Assignment", {
  refresh(frm) {
    frm.set_df_property("custom_basic_pay", "read_only", 1);
    frm.set_df_property("base", "read_only", 1);
    set_values_from_salary_structure(frm);
  },

  salary_structure(frm) {
    set_values_from_salary_structure(frm);
  },

  before_workflow_action(frm) {
    if (frm.selected_workflow_action !== "Reject") {
      return;
    }

    let dialog = new frappe.ui.Dialog({
      title: "Reason for Rejection",
      fields: [
        {
          label: "Reason",
          fieldname: "reject_reason",
          fieldtype: "Link",
          options: "Reject Reason",
          reqd: 1,
          get_query: function () {
            return {
              filters: [["Reject Reason Type", "document_type", "=", frm.doc.doctype]],
            };
          },
        },
      ],
      primary_action_label: "Reject",
      primary_action(values) {
        frappe
          .call({
            method: "set_reject_reason",
            args: {
              doctype: frm.doc.doctype,
              doc_name: frm.doc.name,
              reject_reason: values.reject_reason,
              workflow_state: frm.doc.workflow_state,
              freeze: true,
            },
          })
          .then((res) => {
            if (res.status == "false") {
              frappe.throw(res.message.message);
            } else {
              frappe.msgprint(res.message.message);
              setTimeout(function () {
                window.location.reload();
              }, 2000);
            }
          });

        dialog.hide();
      },
    });
    dialog.show();
  },
});

function set_values_from_salary_structure(frm) {
  if (!frm.doc.salary_structure || frm.doc.docstatus === 1) {
    return;
  }

  frappe.call({
    method: "real_group_hrms.doc_events.salary_structure_assignment.get_salary_structure_assignment_values",
    args: {
      salary_structure: frm.doc.salary_structure,
    },
    callback(r) {
      if (!r.exc) {
        const values = r.message || {};
        frm.set_value("custom_basic_pay", values.basic_pay || 0);
        frm.set_value("base", values.base || 0);
      }
    },
  });
}
