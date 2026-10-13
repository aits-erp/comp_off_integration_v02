def validate(doc, method=None):
    remove_duplicate_dates(doc)


def remove_duplicate_dates(doc):
    """Removes duplicate dates from the holidays table."""
    unique_holidays = []
    seen_dates = set()

    for holiday in doc.get("holidays"):
        if holiday.holiday_date not in seen_dates:
            unique_holidays.append(holiday)
            seen_dates.add(holiday.holiday_date)

    doc.set("holidays", unique_holidays)
    doc.sort_holidays()
