frappe.ui.form.on("User", {
  refresh(frm) {
    set_email_editability(frm);

    if (frm.doc.username) {
      frm.add_custom_button(__("Set Employee"), function () {
        frappe.prompt(
          {
            label: "Employee",
            fieldname: "employee",
            fieldtype: "Link",
            options: "Employee",
          },
          (values) => {
            frappe.call({
              method: "set_user",
              args: {
                employee: values.employee,
                user: frm.doc.name,
              },
              freeze: true,
              freeze_message: "Please Wait",
              callback: function (r) {
                if (!r.exc) {
                  frappe.msgprint(r.message);
                } else {
                  frappe.msgprint("Something went wrong, check logs");
                }
              },
            });
          }
        );
      });
    }
  },

  enabled(frm) {
    set_email_editability(frm);
  },
});

function set_email_editability(frm) {
  if (frm.doc.name === "Administrator") {
    return;
  }

  const email = (frm.doc.email || "").trim();
  const has_email = !!email;
  const allow_edit = !has_email;

  frm.set_df_property("email", "read_only", allow_edit ? 0 : 1);
  frm.toggle_enable("email", allow_edit);
}
