frappe.templates["existing_leave.html"] = `
<div class="form-message yellow">
  <div>{{__("There are existing leaves on the selected date range.")}}</div>
</div>
<table class="table table-bordered table-hover">
  <thead>
    <tr>
      <th style="width: 20%">{{ __("Name") }}</th>
      <th style="width: 20%">{{ __("From Date") }}</th>
      <th style="width: 20%">{{ __("To Date") }}</th>
      <th style="width: 20%">{{ __("Is Half Day") }}</th>
      <th style="width: 20%">{{ __("Half Day Date") }}</th>
      <th style="width: 20%">{{ __("Status") }}</th>
    </tr>
  </thead>

  <tbody>
    {% for(var i=0; i < leaves.length; i++) { %} <tr>
      <td class="small"><a href="{{ frappe.utils.get_form_link("Leave Application",leaves[i].name) }}">{{ leaves[i].name }}</a></td>
      <td class="small"> {{ frappe.datetime.str_to_user(__(leaves[i].from_date)) }} </td>
      <td class="small"> {{ frappe.datetime.str_to_user(__(leaves[i].to_date)) }} </td>
      <td class="small"> {{ __(leaves[i].half_day ? "Yes" : "No") }} </td>
      <td class="small"> {{ frappe.datetime.str_to_user(__(leaves[i].half_day_date)) }} </td>
      <td class="small"> {{ __(leaves[i].status) }} </td>
      </tr>
      {% } %}
  </tbody>
</table>`;

function isCrossDayShift(shiftDetails) {
  if (!shiftDetails) return false;
  return Boolean(
    Number(shiftDetails.custom_is_cross_day) ||
    (shiftDetails.start_time &&
      shiftDetails.end_time &&
      shiftDetails.start_time > shiftDetails.end_time)
  );
}

function parseTimeToSeconds(timeValue) {
  if (!timeValue) return 0;
  const [hours = 0, minutes = 0, seconds = 0] = String(timeValue)
    .split(":")
    .map((part) => Number(part) || 0);
  return hours * 3600 + minutes * 60 + seconds;
}

function formatSecondsToTime(totalSeconds) {
  const normalized = ((Math.round(totalSeconds) % 86400) + 86400) % 86400;
  const hours = String(Math.floor(normalized / 3600)).padStart(2, "0");
  const minutes = String(Math.floor((normalized % 3600) / 60)).padStart(2, "0");
  const seconds = String(normalized % 60).padStart(2, "0");
  return `${hours}:${minutes}:${seconds}`;
}

function getShiftDurationSeconds(shiftDetails) {
  const startSeconds = parseTimeToSeconds(shiftDetails.start_time);
  let endSeconds = parseTimeToSeconds(shiftDetails.end_time);

  if (isCrossDayShift(shiftDetails) && endSeconds <= startSeconds) {
    endSeconds += 86400;
  }

  return Math.max(endSeconds - startSeconds, 0);
}

function getHalfDayThresholdSeconds(shiftDetails) {
  const configuredThreshold = parseTimeToSeconds(
    shiftDetails.custom_working_hours_threshold_for_half_day
  );
  if (configuredThreshold > 0) {
    return configuredThreshold;
  }

  return Math.floor(getShiftDurationSeconds(shiftDetails) / 2);
}

function getPrefillTimes(frm, shiftDetails) {
  if (!shiftDetails?.start_time || !shiftDetails?.end_time) {
    return null;
  }

  if (!frm.doc.half_day) {
    return {
      custom_from_time: shiftDetails.start_time,
      custom_to_time: shiftDetails.end_time,
    };
  }

  const halfType = (frm.doc.custom_half_type || "").trim();
  if (!halfType) {
    return null;
  }

  const startSeconds = parseTimeToSeconds(shiftDetails.start_time);
  const thresholdSeconds = Math.min(
    getHalfDayThresholdSeconds(shiftDetails),
    getShiftDurationSeconds(shiftDetails)
  );
  const midpointTime = formatSecondsToTime(startSeconds + thresholdSeconds);

  if (halfType === "Second Half") {
    return {
      custom_from_time: midpointTime,
      custom_to_time: shiftDetails.end_time,
    };
  }

  return {
    custom_from_time: shiftDetails.start_time,
    custom_to_time: midpointTime,
  };
}

async function getShiftDetails(frm) {
  if (!frm.doc.shift) {
    return null;
  }

  if (frm.__attendance_request_shift?.name === frm.doc.shift) {
    return frm.__attendance_request_shift.details;
  }

  const { message } = await frappe.db.get_value("Shift Type", frm.doc.shift, [
    "custom_is_cross_day",
    "start_time",
    "end_time",
    "custom_working_hours_threshold_for_half_day",
  ]);

  if (!message) {
    return null;
  }

  frm.__attendance_request_shift = {
    name: frm.doc.shift,
    details: message,
  };
  return message;
}

async function applyShiftTimePrefill(frm) {
  const shiftDetails = await getShiftDetails(frm);
  const prefillTimes = getPrefillTimes(frm, shiftDetails);
  if (!prefillTimes) {
    return;
  }

  frm.__attendance_request_prefill_in_progress = true;
  await frm.set_value(prefillTimes);
  frm.__attendance_request_prefill_in_progress = false;
}

async function syncHalfDayDate(frm) {
  if (frm.doc.half_day && frm.doc.from_date && frm.doc.to_date && frm.doc.from_date === frm.doc.to_date) {
    if (frm.doc.half_day_date !== frm.doc.from_date) {
      await frm.set_value("half_day_date", frm.doc.from_date);
    }
    return;
  }

  if (!frm.doc.half_day && frm.doc.half_day_date) {
    await frm.set_value("half_day_date", null);
  }
}

function fetchClosestShiftForTime(frm) {
  if (
    !frm.doc.from_date ||
    !frm.doc.employee ||
    !frm.doc.custom_from_time ||
    frm.__attendance_request_prefill_in_progress
  ) {
    return;
  }

  frappe.call({
    method: "real_group_hrms.api.attendance_request.closest_shift_for_time",
    args: {
      from_time: frm.doc.custom_from_time,
      to_time: frm.doc.custom_to_time,
      date: frm.doc.from_date,
      employee: frm.doc.employee,
    },
    callback: async function (r) {
      if (r.message) {
        frm.__attendance_request_shift_set_from_time = true;
        await frm.set_value("shift", r.message);
        frm.__attendance_request_shift_set_from_time = false;
        await validateRequestTimeWindow(frm);
      }
    },
  });
}

async function validateRequestTimeWindow(frm) {
  const { shift, from_date, to_date, custom_from_time, custom_to_time } = frm.doc;

  if (!shift || !from_date || !to_date || !custom_from_time || !custom_to_time) {
    return;
  }

  const shiftDetails = await getShiftDetails(frm);
  if (!shiftDetails || isCrossDayShift(shiftDetails)) {
    return;
  }

  if (from_date === to_date && custom_to_time <= custom_from_time) {
    frappe.msgprint(__("To Time must be after From Time for non-cross-day shifts."));
    await frm.set_value("custom_to_time", null);
  }
}

frappe.ui.form.on("Attendance Request", {
  shift: async (frm) => {
    if (!frm.doc.employee || !frm.doc.from_date) {
      frappe.throw(__("Please select Employee and From Date first"));
    }

    if (!frm.__attendance_request_shift_set_from_time) {
      await applyShiftTimePrefill(frm);
    }

    await validateRequestTimeWindow(frm);
  },
  employee: async (frm) => {
    frappe.call({
      method: "real_group_hrms.tasks.process_employee_checkin.get_employee_allowed_shifts",
      args: {
        for_date: frm.doc.from_date,
        employee: frm.doc.employee,
      },
      callback: function (r) {
        if (r.message) {
          frm.set_query("shift", function () {
            return {
              filters: {
                name: ["in", r.message],
              },
            };
          });
        }
      },
    });

    await frm.trigger("set_custom_attendance_approver");
  },
  custom_from_time: async (frm) => {
    fetchClosestShiftForTime(frm);
    await validateRequestTimeWindow(frm);
  },
  custom_to_time: async (frm) => {
    fetchClosestShiftForTime(frm);
    await validateRequestTimeWindow(frm);
  },
  before_workflow_action: (frm) => {
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
          if (values.reject_reason) {
            frappe
              .call({
                method: "set_reject_reason",
                args: {
                  doctype: frm.doc.doctype,
                  doc_name: frm.doc.name,
                  reject_reason: values.reject_reason,
                  workflow_state: frm.doc.workflow_state,
                  freeze: true,
                },
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
          }
        },
      });
      dialog.show();
    }
  },
  half_day: async (frm) => {
    if (!frm.doc.half_day) {
      await frm.set_value("custom_half_type", "");
    }

    await syncHalfDayDate(frm);

    if (frm.doc.half_day && !frm.doc.custom_half_type) {
      await frm.set_value("custom_half_type", "First Half");
    }

    await applyShiftTimePrefill(frm);
  },
  custom_half_type: async (frm) => {
    await applyShiftTimePrefill(frm);
    await validateRequestTimeWindow(frm);
  },
  to_date: async (frm) => {
    await syncHalfDayDate(frm);
    await validateRequestTimeWindow(frm);
  },
  from_date: async (frm) => {
    await syncHalfDayDate(frm);
    await validateRequestTimeWindow(frm);
  },
  refresh: (frm) => {
    frm.set_df_property("shift", "read_only", 0);

    if (frm.is_new() && frm.doc.employee && !frm.doc.custom_attendance_approver) {
      frm.trigger("set_custom_attendance_approver");
    }

    if (frm.doc.from_date && frm.doc.to_date && frm.doc.employee) {
      frappe.call({
        method: "real_group_hrms.api.attendance_request.get_leave_on_dates",
        args: {
          employee: frm.doc.employee,
          from_date: frm.doc.from_date,
          to_date: frm.doc.to_date,
        },
        callback: function (r) {
          if (r.message) {
            const leaves = r.message;
            if (leaves.length < 1) return;
            frm.dashboard.add_section(
              frappe.render_template("existing_leave.html", {
                leaves: r.message || [],
              }),
              __("Existing Leaves")
            );
          }
        },
      });
    }
  },
  set_custom_attendance_approver: async (frm) => {
    if (!frm.doc.employee || !frm.fields_dict.custom_attendance_approver) {
      return;
    }

    const { message } = await frappe.call({
      method: "hrms.api.get_leave_approval_details",
      args: {
        employee: frm.doc.employee,
      },
    });

    if (!message) {
      return;
    }

    const values = {};
    if (frm.fields_dict.custom_attendance_approver) {
      const approver = message.leave_approver || null;
      if (frm.doc.custom_attendance_approver !== approver) {
        values.custom_attendance_approver = approver;
      }
    }

    if (frm.fields_dict.custom_attendance_approver_name) {
      const approverName = message.leave_approver_name || null;
      if (frm.doc.custom_attendance_approver_name !== approverName) {
        values.custom_attendance_approver_name = approverName;
      }
    }

    if (Object.keys(values).length) {
      await frm.set_value(values);
    }
  },
});
