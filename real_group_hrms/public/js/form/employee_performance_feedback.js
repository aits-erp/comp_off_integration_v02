frappe.ui.form.on("Employee Performance Feedback", {
  appraisal: function (frm) {
    if (frm.doc.appraisal) {
      frm.clear_table("custom_appraiser_feedback_criteria");
      frappe.db.get_value("Appraisal", frm.doc.appraisal, "appraisal_template").then((r) => {
        if (r && r.message) {
          const appraisal_template = r.message.appraisal_template;

          frappe.db.get_doc("Appraisal Template", appraisal_template).then((doc) => {
            const appraiser_feedback_criteria =
              doc.custom_appraiser_feedback_criteria || doc.appraiser_feedback_criteria || [];

            if (appraiser_feedback_criteria.length) {
              appraiser_feedback_criteria.forEach((afc) => {
                let child = frm.add_child("custom_appraiser_feedback_criteria");
                child.feedback_criteria = afc.feedback_criteria;
              });

              frm.refresh_field("custom_appraiser_feedback_criteria");
            }
          });
        }
      });
      frm.refresh_field("custom_appraiser_feedback_criteria");
    }
  },
});
