frappe.listview_settings["Leave Application"] = {
  before_workflow_action: function (listview) {
    console.log(listview.selected_workflow_action);

    let selected_docs = listview.get_checked_items();

    if (listview.selected_workflow_action == "Reject") {
      let dialog = new frappe.ui.Dialog({
        title: "Reason for Rejection",
        fields: [
          {
            label: "Reason",
            fieldname: "reject_reason",
            fieldtype: "Link",
            options: "Reject Reason",
            reqd: 1,
          },
        ],
        primary_action_label: "Reject",
        primary_action(values) {
          if (values.reject_reason) {
            frappe
              .call({
                method: "set_reject_reason",
                args: {
                  docs: selected_docs,
                  doctype: listview.doctype,
                  multi_reject_reason: values.reject_reason,
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
                  }, 1000);
                }
              });

            dialog.hide();
          }
        },
      });
      dialog.show();
    }
  },
};
