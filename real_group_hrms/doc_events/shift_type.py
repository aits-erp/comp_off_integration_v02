from datetime import timedelta

from frappe.utils import format_time, get_time, get_timedelta


def validate(doc, method=None):
    start_delta = get_timedelta(doc.start_time)
    end_delta = get_timedelta(doc.end_time)
    if start_delta < end_delta:
        doc.custom_shift_time = timedelta(seconds=(end_delta - start_delta).total_seconds())
    else:
        doc.custom_shift_time = timedelta(seconds=(end_delta + timedelta(days=1) - start_delta).total_seconds())
    shift_actual_start(doc)


def shift_actual_start(doc):
    grace_period = getattr(doc, "custom_late_entry_grace_period", None)
    if not grace_period:
        return
    grace = get_time(grace_period)
    if doc.start_time and grace:
        actual_start = get_timedelta(doc.start_time) + get_timedelta(format_time(grace))
        doc.custom_actual_start_time = format_time(actual_start)
