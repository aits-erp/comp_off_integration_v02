// Copyright (c) 2024, Step Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Skip Loan Installment", {
    refresh(frm) {
        frm.set_query("active_loans", function () {
            return {
                query: "real_group_hrms.real_group.doctype.skip_loan_installment.skip_loan_installment.get_employee_advance",
                filters: {
                    "employee": frm.doc.employee,
                },
            };
        });

        frm.set_query("loan_installment", function () {
            return {
                filters: {
                    "ref_docname": frm.doc.active_loans,
                    "docstatus": 1
                },
            };
        });
    },

    // validate(frm) {

    //     const rowsToRemove = [];
    //     frm.doc.upcoming_installment.forEach((rec, index) => {
    //         if (rec.skip === 0) {
    //             rowsToRemove.push(index);
    //         }
    //     });
    //     for (let i = rowsToRemove.length - 1; i >= 0; i--) {
    //         const rowIndex = rowsToRemove[i];
    //         frm.get_field("upcoming_installment").grid.grid_rows[rowIndex].remove();
    //     }
    // },

    employee(frm) {
        // console.log(frm.doc.employee);
    },

    active_loans(frm) {
        // console.log(frm.doc.active_loans);
        // frappe.call({
        //     method: 'real_group_hrms.real_group.doctype.skip_loan_installment.skip_loan_installment.get_additional_salary',
        //     args: {
        //         'employee': frm.doc.employee,
        //         'ref_doctype': "Employee Advance",
        //         'ref_docname': frm.doc.active_loans,
        //         'posting_date': frm.doc.posting_date
        //     },
        //     callback: function (r) {
        //         if (!r.exc) {
        //             frm.clear_table("upcoming_installment")
        //             let ads = r.message
        //             ads.forEach(rec => {
        //                 let row = frm.fields_dict.upcoming_installment.grid.add_new_row();
        //                 frappe.model.set_value(row.doctype, row.name, "additional_salary", rec.name);
        //                 frappe.model.set_value(row.doctype, row.name, "installment_date", rec.payroll_date);
        //                 frappe.model.set_value(row.doctype, row.name, "amount", rec.amount);
        //             });
        //         }
        //     }
        // });
    }
});
