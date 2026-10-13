frappe.ui.form.on("Medical History", {
  refresh(frm) {
    if (frm.is_new()) {
      frappe.call({
        method: "medical_history_measurement_points_both",
        callback: function (r) {
          if (r.message) {
            var records = r.message;
            cur_frm.clear_table("random_check");
            var desiredOrder = [
              "Body Temperature",
              "Weight",
              "Height",
              "Body Mass Index",
              "Fasting Blood Sugar",
              "Postprandial Blood Sugar",
              "Heart Rate/Pulse",
              "Blood Pressure",
            ];

            var orderLookup = {};
            desiredOrder.forEach((measure, index) => {
              orderLookup[measure] = index;
            });

            records.sort((a, b) => {
              return orderLookup[a.measure_name] - orderLookup[b.measure_name];
            });

            records.forEach((rec) => {
              var row = cur_frm.fields_dict["random_check"].grid.add_new_row();
              frappe.model.set_value(row.doctype, row.name, "medical_parameters", rec.measure_name);
              frappe.model.set_value(row.doctype, row.name, "medical_code", rec.measure_code);
              frappe.model.set_value(row.doctype, row.name, "uom", rec.uom);
            });
          }
        },
      });
    }
  },

  onload: function (frm) {
    let tables = [
      "random_check",
      "biochemistry",
      "complete_blood_count",
      "differential_leucocyte_count",
      "kidney_function_test",
      "liver_function_test",
      "lipid_profile_test",
      "urine_physical_examination",
      "urine_chemical_examination",
      "urine_microscopic_examination",
      "pulmonary_function_test",
      "general_examination",
      "cardiovascular_system",
      "respiratory_system",
      "gastrointestinal_system",
      "examination_of_eyes",
      "individual_colour_identification",
      "gastro_urinary_system",
      "audiomentry_examination",
      "menstrual_and_obstetric_history",
    ];
    tables.forEach(function (table) {
      if (frm.fields_dict[table]) {
        frm.get_field(table).grid.cannot_add_rows = true;
        frm.set_df_property(table, "cannot_add_rows", true);
        frm.get_field(table).grid.refresh();
      }
    });
  },
  date_of_birth(frm) {
    if (frm.doc.date_of_birth != null) {
      frm.set_value("age", moment().diff(frm.doc.date_of_birth, "years"));
    }
  },

  date_of_joining(frm) {
    if (frm.doc.date_of_joining != null) {
      frm.set_value("service_years", moment().diff(frm.doc.date_of_joining, "years"));
    }
  },

  type_of_examination(frm) {
    setTimeout(function () {
      frappe.call({
        method: "medical_history_measurement_points",
        args: {
          type_of_examination: frm.doc.type_of_examination,
        },
        callback: function (r) {
          if (r.message) {
            var records = r.message;

            records.forEach((rec) => {
              if (rec.parameter_type !== "Random Check") {
                try {
                  let inputString = rec.parameter_type;
                  let outputString = convertToSnakeCase(inputString);
                  console.log(outputString, inputString);
                  var row = cur_frm.fields_dict[outputString].grid.add_new_row();
                  frappe.model.set_value(row.doctype, row.name, "medical_parameters", rec.measure_name);
                  frappe.model.set_value(row.doctype, row.name, "medical_code", rec.measure_code);
                  frappe.model.set_value(row.doctype, row.name, "uom", rec.uom);
                } catch (error) {
                  console.error(`Error processing record for ${rec.parameter_type}: ${error.message}`);
                }
              }
            });
          }
        },
      });
    }, 2000);
  },
});

function convertToSnakeCase(str) {
  let sanitizedStr = str.replace(/[^\w\s]/gi, "");
  sanitizedStr = sanitizedStr.toLowerCase();
  sanitizedStr = sanitizedStr.replace(/\s+/g, "_");
  return sanitizedStr;
}

frappe.ui.form.on("Attachment Type", {
  attachment_type: function (frm, cdt, cdn) {
    var row = frappe.get_doc(cdt, cdn);
    if (row.attachment_type !== "Form 21") {
      frappe.model.set_value(
        row.doctype,
        row.name,
        "allowed_formats",
        "Formats allowed are JPEG and JPG with max 1 MB"
      );
    } else {
      frappe.model.set_value(
        row.doctype,
        row.name,
        "allowed_formats",
        "Formats allowed are JPEG, JPG and PDF with max 1 MB"
      );
    }
  },
});
