frappe.ui.form.on("Employee Grade", {
  refresh(frm) {
    frm.set_query("custom_allowed_check_in_machines", function (doc, cdt, cdn) {
      return {
        filters: {
          machine_type: "In",
        },
      };
    });
    frm.set_query("custom_allowed_check_out_machines", function (doc, cdt, cdn) {
      return {
        filters: {
          machine_type: "Out",
        },
      };
    });
  },
  validate(frm) {
    if (!frm.doc.custom_late_entry_grace_period) {
      frm.set_value("custom_late_entry_grace_period", "");
    }
    if (!frm.doc.custom_hours_per_leave) {
      frm.set_value("custom_hours_per_leave", "");
    }
  },

  custom_present_on_holiday: function (frm) {
    if (frm.doc.custom_present_on_holida != frm.doc.custom_extra_work_hour) {
      frm.set_value("custom_extra_work_hour", frm.doc.custom_present_on_holiday);
      frm.trigger("hide_compensation_fields");
    }
  },

  custom_no_punch_applicable: function (frm) {
    frm.events.hide_short_leave_section(frm);
  },

  custom_single_punch_applicable: function (frm) {
    frm.events.hide_short_leave_section(frm);
  },
  custom_extra_work_hour: function (frm) {
    if (frm.doc.custom_present_on_holida != frm.doc.custom_extra_work_hour) {
      frm.set_value("custom_present_on_holiday", frm.doc.custom_extra_work_hour);
      frm.trigger("hide_compensation_fields");
    }
  },
  hide_compensation_fields(frm) {
    if (frm.doc.custom_present_on_holiday === "Comp Off") {
      frm.set_df_property("custom_incentive_gross_amount", "hidden", 1);
      frm.set_df_property("custom_incentive_ceiling", "hidden", 1);
      frm.set_df_property("custom_comp_off_validity", "hidden", 0);
    } else {
      frm.set_df_property("custom_incentive_gross_amount", "hidden", 0);
      frm.set_df_property("custom_incentive_ceiling", "hidden", 0);
      frm.set_df_property("custom_comp_off_validity", "hidden", 1);
    }
  },
  hide_short_leave_section: function (frm) {
    if (frm.doc.custom_no_punch_applicable == 1 || frm.doc.custom_single_punch_applicable == 1) {
      frm.set_df_property("custom_short_leave_type", "hidden", 1);
      frm.set_df_property("custom_number_of_leaves", "hidden", 1);
      frm.set_df_property("custom_hours_per_leave", "hidden", 1);
    } else {
      frm.set_value("custom_short_leave_type", "");
      frm.set_value("custom_number_of_leaves", "");
      frm.set_value("custom_hours_per_leave", "");
      frm.set_df_property("custom_short_leave_type", "hidden", 0);
      frm.set_df_property("custom_number_of_leaves", "hidden", 0);
      frm.set_df_property("custom_hours_per_leave", "hidden", 0);
    }
  },
});
