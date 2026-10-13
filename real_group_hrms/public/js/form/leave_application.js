frappe.ui.form.on("Leave Application", {
  from_date: function (frm) {
    validate_dates(frm);
    validate_employee_not_resigned(frm);
  },

  to_date: function (frm) {
    validate_dates(frm);
    validate_employee_not_resigned(frm);
  },
  half_day: function (frm) {
    if (frm.doc.half_day === 0) {
      frm.set_value("custom_half_type", "");
    }
    if (frm.doc.half_day && frm.doc.to_date != frm.doc.from_date) {
      frm.set_df_property("half_day_date", "reqd", 1);
    }
  },

  leave_type: function (frm) {
    if (frm.doc.leave_type == "Only Gate Pass") {
      frm.set_value("custom_skip_gate_pass", 0);
    }
  },

  before_workflow_action: (frm) => {
    if (frm.doc.custom_reject_reason === "") {
      frappe.throw("set reason");
    }
    if (frm.selected_workflow_action == "Reject") {
      let dialog = new frappe.ui.Dialog({
        title: "Reason for Rejection",
        fields: [
          {
            label: "Reason",
            fieldname: "reject_reason",
            fieldtype: "Link",
            options: "Reject Reason",
            reqd: 1,
            get_query: function () {
              return {
                filters: [["Reject Reason Type", "document_type", "=", frm.doc.doctype]],
              };
            },
          },
        ],
        primary_action_label: "Reject",
        primary_action(values) {
          if (values.reject_reason !== "") {
            frappe
              .call({
                method: "set_reject_reason",
                args: {
                  doctype: frm.doc.doctype,
                  doc_name: frm.doc.name,
                  reject_reason: values.reject_reason,
                  workflow_state: frm.doc.workflow_state,
                },
                freeze: true,
                async: false,
              })
              .then((res) => {
                if (res.status == "false") {
                  frappe.throw(res.message.message);
                } else {
                  frappe.msgprint(res.message.message);
                  setTimeout(function () {
                    window.location.reload();
                  }, 2000);
                }
              });

            dialog.hide();
          } else {
            frappe.throw("Hi");
          }
        },
      });
      dialog.show();
    }
  },
});

function validate_employee_not_resigned(frm) {
  if (!frm.doc.employee || !frm.doc.to_date || !frm.doc.__islocal) {
    return;
  }
  frappe.db
    .get_value("Employee", frm.doc.employee, [
      "resignation_letter_date",
      "relieving_date",
    ])
    .then((r) => {
      const values = r.message || {};
      const dates = [values.resignation_letter_date, values.relieving_date].filter(
        Boolean
      );
      if (!dates.length) {
        return;
      }
      const cutoff_date = dates.sort()[0];
      if (frm.doc.to_date >= cutoff_date) {
        frm.set_value("to_date", "");
        frappe.throw(
          __(
            "Cannot apply for leave on or after {0} as Resignation Letter Date/Relieving Date is set in the Employee master.",
            [frappe.datetime.str_to_user(cutoff_date)]
          )
        );
      }
    });
}

function validate_dates(frm) {
  if (frm.doc.from_date || frm.doc.to_date) {
    if (!frm.doc.employee) {
      frm.set_value("from_date", "");
      frm.set_value("to_date", "");
      frappe.throw(__("Please select Employee before setting dates"));
    }
    if (!frm.doc.leave_type) {
      frm.set_value("from_date", "");
      frm.set_value("to_date", "");
      frappe.throw(__("Please select Leave Type before setting dates"));
    }
  }
}

// Comp-Off source-credit selection. Allocation and expiry stay server-side in
// the existing attendance/ledger flows; this only makes consumption auditable.
frappe.ui.form.on("Leave Application", {
  refresh(frm) {
    configure_comp_off_fields(frm);
  },
  employee(frm) {
    clear_comp_off_sources(frm);
    configure_comp_off_fields(frm);
  },
  leave_type(frm) {
    clear_comp_off_sources(frm);
    configure_comp_off_fields(frm);
  },
  custom_comp_off_source_request(frm) {
    refresh_comp_off_worked_dates(frm);
    warn_comp_off_fifo_order(frm);
  },
});

function clear_comp_off_sources(frm) {
  if (frm.fields_dict.custom_comp_off_source_request) {
    frm.clear_table("custom_comp_off_source_request");
    frm.refresh_field("custom_comp_off_source_request");
  }
}

function configure_comp_off_fields(frm) {
  if (!frm.fields_dict.custom_comp_off_source_request) return;
  if (!frm.doc.leave_type) {
    set_comp_off_field_state(frm, false);
    return;
  }
  frappe.db.get_value("Leave Type", frm.doc.leave_type, "is_compensatory").then((response) => {
    set_comp_off_field_state(frm, Number(response.message?.is_compensatory || 0) === 1);
  });
}

function set_comp_off_field_state(frm, isCompOff) {
  frm.toggle_display("custom_comp_off_source_request", isCompOff);
  frm.toggle_display("custom_comp_off_available_work_date", isCompOff);
  frm.set_df_property("custom_comp_off_source_request", "reqd", isCompOff);
  if (!isCompOff) {
    clear_comp_off_sources(frm);
    frm.set_value("custom_comp_off_available_work_date", "");
  }
  frm.set_query("custom_comp_off_source_request", () => ({
    query: "real_group_hrms.api.comp_off.get_available_comp_off_requests",
    filters: { employee: frm.doc.employee, leave_type: frm.doc.leave_type },
  }));
  refresh_comp_off_worked_dates(frm);
}

function refresh_comp_off_worked_dates(frm) {
  if (!frm.fields_dict.custom_comp_off_available_work_date) return;
  const names = (frm.doc.custom_comp_off_source_request || [])
    .map((row) => row.compensatory_leave_request)
    .filter(Boolean);
  if (!names.length) {
    frm.set_value("custom_comp_off_available_work_date", "");
    return;
  }
  frappe.db.get_list("Compensatory Leave Request", {
    filters: { name: ["in", names] },
    fields: ["work_from_date"],
    order_by: "work_from_date asc",
  }).then((rows) => {
    frm.set_value(
      "custom_comp_off_available_work_date",
      rows.map((row) => frappe.datetime.str_to_user(row.work_from_date)).join(", ")
    );
  });
}

function warn_comp_off_fifo_order(frm) {
  const selectedNames = (frm.doc.custom_comp_off_source_request || [])
    .map((row) => row.compensatory_leave_request)
    .filter(Boolean);
  if (!selectedNames.length || !frm.doc.employee || !frm.doc.leave_type) return;
  frappe.call({
    method: "real_group_hrms.api.comp_off.get_available_comp_off_dates",
    args: { employee: frm.doc.employee, leave_type: frm.doc.leave_type },
    callback(response) {
      const expected = (response.message || []).slice(0, selectedNames.length);
      const skipped = expected.filter((row) => !selectedNames.includes(row.name));
      if (skipped.length) {
        frappe.show_alert({
          message: __("Older worked-holiday credit(s) dated {0} are still unused. Consider using Compensatory Off oldest-first (FIFO).", [
            skipped.map((row) => frappe.datetime.str_to_user(row.work_date)).join(", "),
          ]),
          indicator: "orange",
        }, 8);
      }
    },
  });
}
