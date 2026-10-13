frappe.listview_settings["Attendance"] = {
  onload: function (listview) {
    cur_list.page.remove_inner_button("Mark Attendance");
  },
};
