frappe.ui.form.on("Compensation Matrix", {
  refresh(frm) {
    $.each(frm.doc.items || [], function (i, item) {
      var fromParts = item.from_hrs.split(":");
      var toParts = item.to_hrs.split(":");

      fromParts[0] = fromParts[0].padStart(2, "0");
      toParts[0] = toParts[0].padStart(2, "0");

      var formattedFromHrs = fromParts.join(":");
      var formattedToHrs = toParts.join(":");

      if (formattedFromHrs > formattedToHrs) {
        frappe.throw("Extra Hours Start must be less than Extra hours end");
      }
    });
  },
});

frappe.ui.form.on("Compensation Matrix Details", {
  refresh(frm, cdt, cdn) {
    // Your code here
    let row = frappe.get_doc(cdt, cdn);
    if (row.c_off_credit % 1 !== 0 && row.c_off_credit % 1 !== 0.5)
      frappe.throw(__("Value for C Off Credit must end in .0 or .5"));
    frappe.validated = false;
  },

  c_off_credit(frm, cdt, cdn) {
    let row = frappe.get_doc(cdt, cdn);
    if (row.c_off_credit % 1 !== 0 && row.c_off_credit % 1 !== 0.5)
      frappe.throw(__("Value for C Off Credit must end in .0 or .5"));
    frappe.validated = false;
  },
});
