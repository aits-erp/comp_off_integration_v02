// Copyright (c) 2024, Step Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Loan Purpose", {
	refresh(frm) {

	},

    loan_amount: function(frm) {
        frm.trigger("set_installment_amount");
    },

    number_of_installments: function(frm) {
        frm.trigger("set_installment_amount");
    },

    set_installment_amount: function(frm) {
        frm.set_value("installment_amount", (frm.doc.loan_amount / frm.doc.number_of_installments));
    }
});
