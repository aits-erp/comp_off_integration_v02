frappe.ui.form.on("Real Group User", {
  first_name: function (frm) {
    frm.events.set_full_name(frm);
  },
  middle_name: function (frm) {
    frm.events.set_full_name(frm);
  },
  last_name: function (frm) {
    frm.events.set_full_name(frm);
  },
  set_full_name: function (frm) {
    if (frm.doc.first_name !== undefined && frm.doc.first_name !== "") {
      let full_name = frm.doc.first_name;

      if (frm.doc.middle_name !== undefined && frm.doc.middle_name !== "") {
        full_name += " " + frm.doc.middle_name;
      }

      if (frm.doc.last_name !== undefined && frm.doc.last_name !== "") {
        full_name += " " + frm.doc.last_name;
      }

      frm.set_value("full_name", full_name.trim());
    }
  },
});
