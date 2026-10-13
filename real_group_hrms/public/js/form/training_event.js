frappe.ui.form.on("Training Event", {
    refresh(frm) {
        frm.events.toggle_employee_requirement(frm);
    },

    event_status(frm) {
        frm.events.toggle_employee_requirement(frm);
    },

    validate(frm) {
        if (frm.doc.event_status !== "Completed") {
            return;
        }

        const has_employee = (frm.doc.employees || []).some((row) => row.employee);
        if (!has_employee) {
            frappe.throw(__("Employees are mandatory when Event Status is Completed."));
        }
    },

    toggle_employee_requirement(frm) {
        frm.set_df_property("employees", "reqd", frm.doc.event_status === "Completed");
    },
});
