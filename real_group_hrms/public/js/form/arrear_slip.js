frappe.ui.form.on("Arrear Slip", {
  start_date: function (frm) {
    if (frm.doc.start_date && frm.doc.payroll_frequency == "Monthly") {
      const startDate = frappe.datetime.str_to_obj(frm.doc.start_date);
      const year = startDate.getFullYear();
      const month = startDate.getMonth() + 1;
      const day = startDate.getDate() - 1;

      const endDate = new Date(year, month, day);
      frm.set_value("end_date", frappe.datetime.obj_to_str(endDate));
    }
    if (frm.doc.employee && frm.doc.end_date) {
      frappe.call({
        method: "hrms.hr.doctype.leave_application.leave_application.get_leave_details",
        args: {
          employee: frm.doc.employee,
          date: frm.doc.end_date,
          is_additional: true,
        },
        callback: function (r) {
          console.log(r);
          if (r.message) {
            const leaveDetails = r.message.leave_allocation;
            frm.clear_table("leave_details");

            for (const leaveType in leaveDetails) {
              const leaveValues = leaveDetails[leaveType];
              const row = frm.add_child("leave_details");
              row.leave_type = leaveType;
              row.total_allocated_leaves = flt(leaveValues.total_leaves);
              row.expired_leaves = flt(leaveValues.expired_leaves);
              row.used_leaves = flt(leaveValues.leaves_taken);
              row.pending_leaves = flt(leaveValues.leaves_pending_approval);
              row.available_leaves = flt(leaveValues.remaining_leaves);
            }

            frm.refresh_field("leave_details");
          }
        },
      });
    }
  },
});
