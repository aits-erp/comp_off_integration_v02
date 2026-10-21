def validate(doc, method=None):
    validate_allowed_shift(doc)


def validate_allowed_shift(doc):
    if doc.custom_no_punch_applicable:
        doc.set("custom_allowed_shifts", [])
    print(doc.custom_allowed_shifts)
