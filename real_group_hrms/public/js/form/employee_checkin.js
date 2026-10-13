frappe.ui.form.on("Employee Checkin", {
  employee: async (frm) => {
    hide_location_fields(frm);
    frm.remove_custom_button("Fetch Location");
    const r = await frappe.db.get_value("Employee", frm.doc.employee, "custom_is_remote_office");

    if (r.message && r.message.custom_is_remote_office) {
      frm.add_custom_button(__("Fetch Location"), function () {
        fetch_geolocation(frm);
      });
      fetch_geolocation(frm);
      show_location_fields(frm);
    }
  },
  refresh: async (frm) => {
    const r = await frappe.db.get_value("Employee", frm.doc.employee, "custom_is_remote_office");
    frm.trigger("hide_location_fields");
    if (r.message && r.message.custom_is_remote_office) {
      if (frm.doc.custom_latitude && frm.doc.custom_longitude) {
        show_location_fields(frm);
      }
    }
  },
  before_save: async (frm) => {
    const r = await frappe.db.get_value("Employee", frm.doc.employee, "custom_is_remote_office");

    if (r.message && r.message.custom_is_remote_office) {
      if (!frm.doc.custom_latitude || !frm.doc.custom_longitude) {
        frappe.msgprint({
          message: __("Please fetch your location before saving"),
          title: __("Location Required"),
          indicator: "red",
        });
        frappe.validated = false;
      }
    }
  },
});

function hide_location_fields(frm) {
  frm.set_df_property("custom_latitude", "hidden", 1);
  frm.set_df_property("custom_longitude", "hidden", 1);
  frm.set_df_property("custom_location", "hidden", 1);
}

function show_location_fields(frm) {
  frm.set_df_property("custom_latitude", "hidden", 0);
  frm.set_df_property("custom_longitude", "hidden", 0);
  frm.set_df_property("custom_location", "hidden", 0);
}

const fetch_geolocation = async (frm) => {
  if (!navigator.geolocation) {
    frappe.msgprint({
      message: __("Geolocation is not supported by your current browser"),
      title: __("Geolocation Error"),
      indicator: "red",
    });
    return;
  }

  frappe.dom.freeze(__("Fetching your geolocation") + "...");

  navigator.geolocation.getCurrentPosition(
    async (position) => {
      frm.set_value("custom_latitude", position.coords.latitude);
      frm.set_value("custom_longitude", position.coords.longitude);

      await frm.call("set_geolocation");
      frappe.dom.unfreeze();
    },
    (error) => {
      frappe.dom.unfreeze();

      let msg = __("Unable to retrieve your location") + "<br><br>";
      if (error) {
        msg += __("ERROR({0}): {1}", [error.code, error.message]);
      }
      frappe.msgprint({
        message: msg,
        title: __("Geolocation Error"),
        indicator: "red",
      });
    }
  );
};
