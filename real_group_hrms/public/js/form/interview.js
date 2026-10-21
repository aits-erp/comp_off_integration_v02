frappe.ui.form.on("Interview", {
  custom_open_link: function (frm) {
    window.open(frm.doc.resume_link);
  },
});
