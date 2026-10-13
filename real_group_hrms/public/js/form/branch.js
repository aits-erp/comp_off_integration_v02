const MAX_ALLOWED_MIS_PUNCH_DAYS = 28;

frappe.ui.form.on("Branch", {
	refresh(frm) {
		setup_allowed_mis_punch_days_limit(frm);
	},
	custom_allowed_mis_punch_days(frm) {
		limit_allowed_mis_punch_days(frm);
	},
});

function setup_allowed_mis_punch_days_limit(frm) {
	const field = frm.get_field("custom_allowed_mis_punch_days");
	const input = field && field.$input && field.$input.get(0);

	if (!input || input.dataset.allowedMisPunchDaysLimitApplied) {
		return;
	}

	input.dataset.allowedMisPunchDaysLimitApplied = "1";
	input.setAttribute("maxlength", "2");

	input.addEventListener("beforeinput", (event) => {
		if (event.inputType !== "insertText" || !event.data || !/\d/.test(event.data)) {
			return;
		}

		const start = input.selectionStart || 0;
		const end = input.selectionEnd || 0;
		const next_value = `${input.value.slice(0, start)}${event.data}${input.value.slice(end)}`;
		const next_digits = get_digits(next_value);

		if (next_digits.length > 2 || cint(next_digits) > MAX_ALLOWED_MIS_PUNCH_DAYS) {
			event.preventDefault();
		}
	});

	input.addEventListener("input", () => {
		limit_allowed_mis_punch_days(frm, input.value);
	});
}

function limit_allowed_mis_punch_days(frm, input_value) {
	const value =
		input_value === undefined ? frm.doc.custom_allowed_mis_punch_days : input_value;
	const limited_value = get_limited_value(value);

	if (String(limited_value) !== String(value)) {
		frm.set_value("custom_allowed_mis_punch_days", limited_value);
	}
}

function get_limited_value(value) {
	if (value === undefined || value === null || value === "") {
		return value;
	}

	const digits = get_digits(value).slice(0, 2);

	if (!digits) {
		return "";
	}

	return Math.min(cint(digits), MAX_ALLOWED_MIS_PUNCH_DAYS);
}

function get_digits(value) {
	return String(value).replace(/\D/g, "");
}
