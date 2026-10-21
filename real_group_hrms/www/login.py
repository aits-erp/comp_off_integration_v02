from frappe.www.login import get_context as frappe_get_context

no_cache = True


def get_context(context):
	return frappe_get_context(context)
