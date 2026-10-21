frappe.listview_settings["bioattendancelog"] = {
  onload(listview) {
    if (listview.view_name === "Report") return;
    listview.page.clear_primary_action();
    listview.page.clear_actions_menu();

    const allowedRoles = ["HR User", "HR Manager", "Payroll-CREASX", "Payroll-R"];
    const canResetLogs = allowedRoles.some((role) => frappe.user.has_role(role));

    if (!canResetLogs) return;

    let resetButton;

    const addResetButton = () => {
      if (resetButton) return;
      resetButton = listview.page.add_inner_button(__("Reset Logs"), async () => resetLogs(listview));
    };

    const removeResetButton = () => {
      if (!resetButton) return;
      resetButton.remove();
      resetButton = null;
    };

    const toggleResetButton = () => {
      listview.page.clear_primary_action();
      const hasSelection = listview.get_checked_items(true).length > 0;
      hasSelection ? addResetButton() : removeResetButton();
    };

    listview.$page.on("click", () => setTimeout(toggleResetButton, 5));

    listview.before_refresh = () => {
      removeResetButton();
    };

    toggleResetButton();
  },
  refresh(listview) {
    listview.page.clear_primary_action();
    listview.page.clear_actions_menu();
  },
};

function resetLogs(listview) {
  const logNames = listview.get_checked_items(true);

  if (!logNames.length) {
    frappe.msgprint(__("Select at least one log to reset."));
    return;
  }

  frappe.confirm(__("Set Is Processed to N for the selected logs?"), async () => {
    const { message } = await frappe.call({
      method: "real_group_hrms.real_group.doctype.bioattendancelog.bioattendancelog.reset_bioattendance_logs",
      args: { log_names: logNames },
      freeze: true,
      freeze_message: __("Resetting selected logs..."),
    });

    frappe.show_alert({
      message: __("Reset {0} log(s).", [message?.updated || 0]),
      indicator: "green",
    });

    listview.refresh();
  });
}
