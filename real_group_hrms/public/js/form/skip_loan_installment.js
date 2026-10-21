frappe.ui.form.on("Skip Loan Installment", {
  before_workflow_action: (frm) => {
    if (frm.selected_workflow_action == "Reject") {
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
          if (values.reject_reason) {
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
          }
        },
      });
      dialog.show();
    }
  },
});
