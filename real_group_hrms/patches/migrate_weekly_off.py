import frappe


def execute():
    holidays = frappe.get_all("Holiday List", pluck="name")

    for holiday in holidays:
        holiday_doc = frappe.get_doc("Holiday List", holiday)
        dates = [
            {"holiday_date": d.holiday_date, "description": d.description} for d in holiday_doc.holidays if d.weekly_off
        ]

        doc = frappe.get_doc(
            {
                "doctype": "Weekly Off List",
                "from_date": holiday_doc.from_date,
                "to_date": holiday_doc.to_date,
                "holidays": dates,
                "holiday_list_name": holiday_doc.holiday_list_name,
            }
        )
        doc.insert(ignore_if_duplicate=True)
