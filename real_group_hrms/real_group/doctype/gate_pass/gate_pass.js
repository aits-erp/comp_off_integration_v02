// // Copyright (c) 2025, rtCamp and contributors
// // For license information, please see license.txt

async function set_latest_checkout_time(frm) {
  if (!frm.doc.employee || !frm.doc.date) {
    return;
  }
  const r = await frappe.call({
    method: "real_group_hrms.real_group.doctype.gate_pass.gate_pass.get_latest_checkout_time",
    args: {
      employee: frm.doc.employee,
      date: frm.doc.date,
    },
  });

  const new_value = r.message || null;
  const current_value = frm.doc.checkout_time || null;
  if (String(current_value || "") === String(new_value || "")) {
    return;
  }

  frm.set_value("checkout_time", new_value, null, true);
}

frappe.ui.form.on("Gate Pass", {
  refresh(frm) {
    set_latest_checkout_time(frm);
  },
});
