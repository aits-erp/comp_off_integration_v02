// Copyright (c) 2025, rtCamp and contributors
// For license information, please see license.txt
frappe.ui.form.on("Weekly Off List", {
  refresh: function (frm) {
    if (frm.doc.holidays && frm.doc.holidays.length > 0) {
      frm.set_value("total_holidays", frm.doc.holidays.length);
      frm.set_df_property("weekly_off", "read_only", 1);
      frm.fields_dict.get_weekly_off_dates.toggle(false);
    } else {
      frm.set_df_property("weekly_off", "read_only", 0);
      frm.fields_dict.get_weekly_off_dates.toggle(true);
    }
    frm.$wrapper.find('[data-fieldname="clear_table"]').remove();
  },
  from_date: function (frm) {
    if (frm.doc.from_date && !frm.doc.to_date) {
      var a_year_from_start = frappe.datetime.add_months(frm.doc.from_date, 12);
      frm.set_value("to_date", frappe.datetime.add_days(a_year_from_start, -1));
    }
  },
});

frappe.ui.form.on("Weekly Off Holiday", {
  holidays_delete(frm, cdt, cdn) {
    if (!frm.doc.holidays || frm.doc.holidays.length === 0) {
      frm.set_df_property("weekly_off", "read_only", 0);
      frm.set_value("total_holidays", frm.doc.holidays.length);
      frm.fields_dict.get_weekly_off_dates.toggle(true);
    }
  },
});
frappe.tour["Weekly Off List"] = [
  {
    fieldname: "holiday_list_name",
    title: "Holiday List Name",
    description: __("Enter a name for this Holiday List."),
  },
  {
    fieldname: "from_date",
    title: "From Date",
    description: __("Based on your HR Policy, select your leave allocation period's start date"),
  },
  {
    fieldname: "to_date",
    title: "To Date",
    description: __("Based on your HR Policy, select your leave allocation period's end date"),
  },
  {
    fieldname: "weekly_off",
    title: "Weekly Off",
    description: __("Select your weekly off day"),
  },
  {
    fieldname: "get_weekly_off_dates",
    title: "Add Holidays",
    description: __(
      "Click on Add to Holidays. This will populate the holidays table with all the dates that fall on the selected weekly off. Repeat the process for populating the dates for all your annual holidays"
    ),
  },
  {
    fieldname: "holidays",
    title: "Holidays",
    description: __(
      "Here, your weekly offs are pre-populated based on the previous selections. You can add more rows to also add public and national holidays individually."
    ),
  },
];
