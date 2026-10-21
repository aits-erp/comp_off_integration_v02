import frappe


def validate_filters(company, month, year, branch, department, employee):
    if not company:
        frappe.throw(frappe._("Please Select a Company"))

    if not month:
        frappe.throw(frappe._("Please Select a Month"))

    if not year:
        frappe.throw(frappe._("Please Select a Year"))


@frappe.whitelist()
def get_card_details(
    company,
    month,
    year,
    branch=None,
    department=None,
    employee=None,
):
    validate_filters(company, month, year, branch, department, employee)

    month_mapping = {
        "JAN": 1,
        "FEB": 2,
        "MAR": 3,
        "APR": 4,
        "MAY": 5,
        "JUN": 6,
        "JUL": 7,
        "AUG": 8,
        "SEP": 9,
        "OCT": 10,
        "NOV": 11,
        "DEC": 12,
    }

    conditions = ""

    if company:
        conditions = conditions + f"AND company = '{company}'"
    if employee:
        conditions = conditions + f"AND employee = '{employee}'"
    if department:
        conditions = conditions + f"AND department = '{department}'"
    if month:
        month_number = month_mapping.get(month.upper())
        if month_number:
            conditions = conditions + f"AND MONTH(attendance_date) = '{month_number}'"
    if year:
        conditions = conditions + f"AND YEAR(attendance_date) = '{int(year)}'"

    present = frappe.db.sql(
        f"""
        SELECT
            count(name) as total_present
        FROM
            `tabAttendance`
        WHERE
            docstatus = 1
            AND status = 'present'
            {conditions}
    """,
        as_dict=1,
    )

    absent = frappe.db.sql(
        f"""
        SELECT
            count(name) as total_absent
        FROM
            `tabAttendance`
        WHERE
            docstatus = 1
            AND status = 'absent'
            {conditions}
    """,
        as_dict=1,
    )

    late_entry = frappe.db.sql(
        f"""
        SELECT
            count(name) as total_late_entry
        FROM
            `tabAttendance`
        WHERE
            docstatus = 1
            AND late_entry = 1
            {conditions}
    """,
        as_dict=1,
    )

    early_exit = frappe.db.sql(
        f"""
        SELECT
            count(name) as total_early_exit
        FROM
            `tabAttendance`
        WHERE
            docstatus = 1
            AND early_exit = 1
            {conditions}
    """,
        as_dict=1,
    )

    # html = f"<p></p>"

    html = f"""
        <div class="container my-4 m-1">
            <div class="row">
                <!-- Total Present Card -->
                <div class="col-md-3">
                    <div class="card shadow-sm">
                        <div class="card-body">
                            <h6 class="card-title">TOTAL PRESENT (THIS MONTH)</h6>
                            <div class="card-value text-green">{present[0].total_present}</div>
                        </div>
                    </div>
                </div>

                <!-- Total Absent Card -->
                <div class="col-md-3">
                    <div class="card shadow-sm">
                        <div class="card-body">
                            <h6 class="card-title">TOTAL ABSENT (THIS MONTH)</h6>
                            <div class="card-value text-red">{absent[0].total_absent}</div>
                        </div>
                    </div>
                </div>

                <!-- Late Entry Card -->
                <div class="col-md-3">
                    <div class="card shadow-sm">
                        <div class="card-body">
                            <h6 class="card-title">LATE ENTRY (THIS MONTH)</h6>
                            <div class="card-value text-red">{late_entry[0].total_late_entry}</div>
                        </div>
                    </div>
                </div>

                <!-- Early Exit Card -->
                <div class="col-md-3">
                    <div class="card shadow-sm">
                        <div class="card-body">
                            <h6 class="card-title">EARLY EXIT (THIS MONTH)</h6>
                            <div class="card-value text-red">{early_exit[0].total_early_exit}</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        """

    return html


@frappe.whitelist()
def get_chart_details(
    company,
    month,
    year,
    branch=None,
    department=None,
    employee=None,
):
    validate_filters(company, month, year, branch, department, employee)

    month_mapping = {
        "JAN": 1,
        "FEB": 2,
        "MAR": 3,
        "APR": 4,
        "MAY": 5,
        "JUN": 6,
        "JUL": 7,
        "AUG": 8,
        "SEP": 9,
        "OCT": 10,
        "NOV": 11,
        "DEC": 12,
    }

    conditions = ""

    if company:
        conditions = conditions + f"AND company = '{company}'"
    if employee:
        conditions = conditions + f"AND employee = '{employee}'"
    if department:
        conditions = conditions + f"AND department = '{department}'"
    # if division:
    # 	conditions = conditions + f"AND division ='{division}'"
    if month:
        month_number = month_mapping.get(month.upper())
        if month_number:
            conditions = conditions + f"AND MONTH(attendance_date) = '{month_number}'"
    if year:
        conditions = conditions + f"AND YEAR(attendance_date) = '{int(year)}'"

    attendance_count_chart = frappe.db.sql(
        f"""
        SELECT
            count(name) as total,
            status,
            attendance_date
        FROM
            `tabAttendance`
        WHERE
            docstatus = 1
            {conditions}
        GROUP BY
            status, attendance_date
    """,
        as_dict=1,
    )

    # Extract unique dates and statuses
    labels = sorted({entry["attendance_date"] for entry in attendance_count_chart})
    statuses = {entry["status"] for entry in attendance_count_chart}

    # Initialize datasets dictionary with each status having a list of 0s for each date
    datasets = {status: [0] * len(labels) for status in statuses}

    # Map each date to its index for easier access
    date_index = {d: i for i, d in enumerate(labels)}

    # Populate the datasets with actual values
    for entry in attendance_count_chart:
        date_idx = date_index[entry["attendance_date"]]
        datasets[entry["status"]][date_idx] = entry["total"]

    # Convert to final chart format
    chart_data = {
        "labels": [d.strftime("%Y-%m-%d") for d in labels],
        "datasets": [{"name": status, "type": "bar", "values": datasets[status]} for status in statuses],
    }

    return chart_data
