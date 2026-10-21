// Copyright (c) 2024, Step Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("ERP Salary Structure Import", {
    refresh(frm) {
        // Your Code Here
        frm.set_query("income_tax_slab", "details", function () {
            return {
                filters: {
                    "company": frm.doc.company
                }
            };
        })
    },
    get_employee(frm) {
        if (frm.doc.company && frm.doc.branch && frm.doc.employee_category) {
            frappe.db.get_list('Employee', {
                fields: ['name'],
                filters: {
                    company: frm.doc.company,
                    branch: frm.doc.branch,
                    custom_emp_category: frm.doc.employee_category
                },
                limit: 10000
            }).then(records => {
                records.forEach(element => {
                    var row = frm.fields_dict.details.grid.add_new_row();
                    frappe.model.set_value(row.doctype, row.name, "employee", element.name);
                });
            })
        } else {
            frappe.throw("Please Select Company, Branch, Employee Category");
        }
    }
});
