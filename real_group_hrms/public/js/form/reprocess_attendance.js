frappe.ui.form.on("Reprocess Attendance", {
  refresh(frm) {
    frm.set_query("employee", function () {
      return {
        filters: {
          company: frm.doc.company,
          branch: frm.doc.branch,
          division: frm.doc.division,
          department: frm.doc.department,
        },
      };
    });
  },
});
