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

  const updateCompanyFilterState = (report) => {
    const companyFilter = report.get_filter("company");
    if (!companyFilter) {
      return;
    }

    companyFilter.df.reqd = report.get_filter_value("all_company") ? 0 : 1;
    companyFilter.df.mandatory = 0;

    if (companyFilter.set_required) {
      companyFilter.set_required();
    }

    if (companyFilter.set_mandatory) {
      companyFilter.set_mandatory(companyFilter.get_value());
    }
  };

  const refreshReport = (report) => {
    if (report.prepared_report) {
      report.reset_report_view();
      return;
    }

    if (!report._no_refresh) {
      report.refresh(true);
    }
  };

  frappe.query_reports["[New] Month Wise Attendance"] = {
    onload: function (report) {
      updateCompanyFilterState(report);
    },
    filters: [
      {
        fieldname: "all_company",
        fieldtype: "Check",
        label: "All Company",
        default: 0,
        on_change: function (report) {
          const hadEmployee = !!report.get_filter_value("employee");
          updateCompanyFilterState(report);

          report._updating_all_company = true;
          try {
            if (report.get_filter_value("all_company")) {
              report.set_filter_value({ company: null, employee: null });
            } else {
              report.set_filter_value("employee", null);
            }
          } finally {
            report._updating_all_company = false;
          }

          if (!hadEmployee) {
            refreshReport(report);
          }
        },
      },
      {
        fieldname: "company",
        fieldtype: "Link",
        options: "Company",
        label: "Company",
        reqd: 1,
        depends_on: "eval:!doc.all_company",
        on_change: function (report) {
          const hadEmployee = !!report.get_filter_value("employee");
          updateCompanyFilterState(report);
          report.set_filter_value("employee", null);

          if (!report._updating_all_company && !hadEmployee) {
            refreshReport(report);
          }
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
        fieldname: "department",
        fieldtype: "Link",
        options: "Department",
        label: "Department",
        get_query: function () {
          var company = frappe.query_report.get_filter_value("company");
          var all_company = frappe.query_report.get_filter_value("all_company");
          if (!all_company && !company) {
            frappe.throw(__("Please select a company first"));
          }
          if (all_company) {
            return {};
          }
          return {
            filters: [["Department", "company", "=", company]],
          };
        },
      },
      {
        fieldname: "division",
        fieldtype: "Link",
        options: "Division",
        label: "Division",
      },
      {
        fieldname: "employee",
        fieldtype: "Link",
        options: "Employee",
        label: "Employee",
        get_query: function () {
          var company = frappe.query_report.get_filter_value("company");
          var branch = frappe.query_report.get_filter_value("branch");
          var all_company = frappe.query_report.get_filter_value("all_company");
          if (!all_company && !company) {
            frappe.throw(__("Please select a company first"));
          }
          var filters = [];
          if (branch) {
            filters.push(["Employee", "branch", "=", branch]);
          }
          if (!all_company && company) {
            filters.push(["Employee", "company", "=", company]);
          }
          return { filters: filters };
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
        fieldname: "processed_attendance",
        fieldtype: "Check",
        label: "Processed Attendance",
      },
    ],
    formatter: function (value, row, column, data, default_formatter) {
      value = default_formatter(value, row, column, data);
      if (data.sr == "PAYCODE, CARD NO. & NAME") {
        value = `<b>${value}</b>`;
      } else if (data.italic) {
        value = `<i>${value}</i>`;
      }

      if (data.sr == "E Work") {
        if (value && value != "E Work") {
          if (value.includes("-")) {
            value = `<span style="color: red;">${value.replace("-", "")} (less)</span>`;
          } else {
            value = `<span style="color: orange;">${value} (extra)</span>`;
          }
        }
      }
      return value;
    },
  };
})();
