frappe.ui.form.on("Appraisal Template", {
  setup(frm) {
    const appraiser_feedback_criteria = frm.get_field("custom_appraiser_feedback_criteria");
    if (!appraiser_feedback_criteria) return;

    appraiser_feedback_criteria.grid.editable_fields = [{ fieldname: "feedback_criteria", columns: 11 }];
  },
});
