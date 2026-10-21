frappe.ui.form.on("Shift Type", {
  refresh(frm) {
    frm.remove_custom_button("Mark Attendance");
    if (frm.doc.custom_lunch_applicable) {
      frm.set_df_property("custom_lunch_start_time", "reqd", 1);
      frm.set_df_property("custom_lunch_end_time", "reqd", 1);
    } else {
      frm.set_df_property("custom_lunch_start_time", "reqd", 0);
      frm.set_df_property("custom_lunch_end_time", "reqd", 0);
    }
  },
  validate(frm) {
    normalizeGracePeriods(frm);
  },
  start_time(frm) {
    frm.events.update_cross_day(frm);
  },
  end_time(frm) {
    frm.events.update_cross_day(frm);
  },
  update_cross_day(frm) {
    if (frm.doc.start_time && frm.doc.end_time) {
      const start = toFloat(frm.doc.start_time);
      const end = toFloat(frm.doc.end_time);
      if (end < start) {
        frm.set_value("custom_is_cross_day", 1);
      } else {
        frm.set_value("custom_is_cross_day", 0);
      }
    }
  },
  custom_lunch_applicable(frm) {
    frm.trigger("refresh");
  },
});

function normalizeGracePeriods(frm) {
  if (!frm.doc.custom_actual_start_time) {
    frm.set_value("custom_actual_start_time", "");
  }
  if (!frm.doc.custom_early_entry_grace_period) {
    frm.set_value("custom_early_entry_grace_period", "");
  }
  if (!frm.doc.custom_late_entry_grace_period) {
    frm.set_value("custom_late_entry_grace_period", "");
  }
  if (!frm.doc.custom_early_exit_grace_period) {
    frm.set_value("custom_early_exit_grace_period", "");
  }
  if (!frm.doc.custom_late_exit_grace_period) {
    frm.set_value("custom_late_exit_grace_period", "");
  }
  if (!frm.doc.custom_lunch_start_time) {
    frm.set_value("custom_lunch_start_time", "");
  }
  if (!frm.doc.custom_lunch_end_time) {
    frm.set_value("custom_lunch_end_time", "");
  }
}

function toFloat(str) {
  const [h, m, s] = str.split(":").map(Number);
  return h * 3600 + m * 60 + s;
}
