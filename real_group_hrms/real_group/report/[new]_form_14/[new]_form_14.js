// Copyright (c) 2025, rtCamp and contributors
// For license information, please see license.txt

(() => {
  const getYears = () => {
    const currentYear = new Date().getFullYear();
    const pastYears = 5;
    const futureYears = 0;

    const startYear = currentYear - pastYears;
    const endYear = currentYear + futureYears;

    return Array.from({ length: endYear - startYear + 1 }, (_, i) => startYear + i);
  };

  const years = getYears();

  frappe.query_reports["[New] Form 14"] = {
    filters: [
      {
        fieldname: "company",
        fieldtype: "Link",
        options: "Company",
        label: "Company",
        reqd: 1,
        on_change: function () {
          frappe.query_report.set_filter_value("employee", null);
        },
      },
      {
        fieldname: "branch",
        fieldtype: "Link",
        options: "Branch",
        label: "Branch",
        reqd: 1,
      },
      {
        fieldname: "division",
        fieldtype: "Link",
        options: "Division",
        label: "Division",
      },
      {
        fieldname: "department",
        fieldtype: "Link",
        options: "Department",
        label: "Department",
        get_query: function () {
          var company = frappe.query_report.get_filter_value("company");
          if (!company) {
            frappe.throw(__("Please select a company first"));
          }
          return {
            filters: [["Department", "company", "=", company]],
          };
        },
      },
      {
        fieldname: "employee",
        fieldtype: "Link",
        options: "Employee",
        label: "Employee",
        get_query: function () {
          var company = frappe.query_report.get_filter_value("company");
          if (!company) {
            frappe.throw(__("Please select a company first"));
          }
          return {
            filters: [["Employee", "company", "=", company]],
          };
        },
      },
      {
        fieldname: "month",
        fieldtype: "Select",
        label: "Month",
        options: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
        reqd: 1,
      },
      {
        fieldname: "year",
        fieldtype: "Select",
        label: "Year",
        options: years,
        reqd: 1,
      },
      {
        fieldname: "processed_report",
        fieldtype: "Check",
        label: "Processed Report",
      },
    ],
  };
})();
