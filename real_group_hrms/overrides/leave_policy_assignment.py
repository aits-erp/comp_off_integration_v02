# Copyright (c) 2020, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt


import frappe
from frappe.utils import (
    add_months,
    flt,
    get_first_day,
    get_last_day,
    get_quarter_ending,
    get_quarter_start,
    get_year_ending,
    get_year_start,
    getdate,
)
from hrms.hr.doctype.leave_policy_assignment.leave_policy_assignment import (
    LeavePolicyAssignment,
    calculate_pro_rated_leaves,
)

from real_group_hrms.api.employee_transfer import adjust_value


class LeavePolicyAssignmentOverride(LeavePolicyAssignment):
    def get_new_leaves(self, annual_allocation, leave_details, date_of_joining):
        from frappe.model.meta import get_field_precision

        precision = get_field_precision(frappe.get_meta("Leave Allocation").get_field("new_leaves_allocated"))
        current_date = getdate(frappe.flags.current_date) or getdate()
        # Earned Leaves and Compensatory Leaves are allocated by scheduler, initially allocate 0
        if leave_details.is_compensatory:
            new_leaves_allocated = 0
        # if earned leave is being allcated after the effective period, then let them be calculated pro-rata
        elif (
            leave_details.is_earned_leave
            and not leave_details.custom_calculate_based_on_working_days
            and current_date < getdate(self.effective_to)
        ):
            new_leaves_allocated = self.get_leaves_for_passed_period(annual_allocation, leave_details, date_of_joining)
        elif (
            leave_details.custom_calculate_based_on_working_days
            and leave_details.custom_number_of_working_days > 0
            and not leave_details.custom_avail_leave_in_next_calendar_year
        ):
            # calculate leaves based on working days
            new_leaves_allocated = self.get_leaves_for_working_days(leave_details.custom_number_of_working_days)
            new_leaves_allocated = min(annual_allocation, new_leaves_allocated)
        elif (
            leave_details.custom_calculate_based_on_working_days
            and leave_details.custom_number_of_working_days > 0
            and leave_details.custom_avail_leave_in_next_calendar_year
        ):
            # calculate leaves based on working days of previous year
            new_leaves_allocated = self.get_leaves_for_previous_leave_period(
                leave_details.custom_number_of_working_days
            )
        else:
            # calculate pro-rated leaves for other leave types
            new_leaves_allocated = calculate_pro_rated_leaves(
                annual_allocation,
                date_of_joining,
                self.effective_from,
                self.effective_to,
                is_earned_leave=False,
            )

        # leave allocation should not exceed annual allocation as per policy assignment expect when allocation is of earned type and yearly
        if new_leaves_allocated > annual_allocation and not (
            leave_details.is_earned_leave and leave_details.earned_leave_frequency == "Yearly"
        ):
            new_leaves_allocated = annual_allocation
        return flt(new_leaves_allocated, precision)

    def get_leaves_for_working_days(self, on_working_days: int):
        from real_group_hrms.utils import fetch_leaves_for_working_days

        return fetch_leaves_for_working_days(
            self.employee,
            self.effective_from,
            self.effective_to,
            on_working_days,
        )

    def get_leaves_for_passed_period(self, annual_allocation, leave_details, date_of_joining):
        consider_current_period = is_earned_leave_applicable_for_current_period(
            date_of_joining, leave_details.allocate_on_day, leave_details.earned_leave_frequency
        )
        current_date, from_date = self.get_current_and_from_date(date_of_joining)
        periods_passed = self.get_periods_passed(
            leave_details.earned_leave_frequency, current_date, from_date, consider_current_period
        )
        if periods_passed > 0:
            new_leaves_allocated = self.calculate_leaves_for_passed_period(
                annual_allocation, leave_details, date_of_joining, periods_passed, consider_current_period
            )
        else:
            new_leaves_allocated = 0

        return new_leaves_allocated

    def get_current_and_from_date(self, date_of_joining):
        current_date = getdate(frappe.flags.current_date) or getdate()
        if current_date > getdate(self.effective_to):
            current_date = getdate(self.effective_to)

        from_date = getdate(self.effective_from)
        if getdate(date_of_joining) > from_date:
            from_date = getdate(date_of_joining)

        return current_date, from_date

    def get_periods_passed(self, earned_leave_frequency, current_date, from_date, consider_current_period):
        periods_per_year, months_per_period = {
            "Monthly": (12, 1),
            "Quarterly": (4, 3),
            "Half-Yearly": (2, 6),
            "Yearly": (1, 12),
        }.get(earned_leave_frequency)

        periods_passed = calculate_periods_passed(
            current_date, from_date, periods_per_year, months_per_period, consider_current_period
        )

        return periods_passed

    def calculate_leaves_for_passed_period(
        self, annual_allocation, leave_details, date_of_joining, periods_passed, consider_current_period
    ):
        from frappe.utils import get_first_day, get_last_day, getdate
        from hrms.hr.utils import get_monthly_earned_leave as get_periodically_earned_leave

        periodically_earned_leave = get_periodically_earned_leave(
            date_of_joining,
            annual_allocation,
            leave_details.earned_leave_frequency,
            leave_details.rounding,
            pro_rated=False,
        )

        period_end_date = get_pro_rata_period_end_date(consider_current_period)
        join_date = getdate(date_of_joining)
        freq = (leave_details.earned_leave_frequency or "").lower()

        # --- keep your existing logic as base ---
        if getdate(self.effective_from) <= join_date <= period_end_date:
            leaves = get_periodically_earned_leave(
                date_of_joining,
                annual_allocation,
                leave_details.earned_leave_frequency,
                leave_details.rounding,
                get_first_day(date_of_joining),
                get_last_day(date_of_joining),
            )
            leaves += periodically_earned_leave * (periods_passed - 1)
        else:
            leaves = periodically_earned_leave * periods_passed

        # ─────────────────────────────
        # 🔹 Additional Rule — for Quarterly frequency only
        # ─────────────────────────────
        if freq == "quarterly" and not getdate(join_date) <= getdate(self.effective_from):
            month = join_date.month
            quarter_start_month = ((month - 1) // 3) * 3 + 1
            quarter_months = [quarter_start_month, quarter_start_month + 1, quarter_start_month + 2]

            join_month_index = quarter_months.index(month)  # 0, 1, or 2
            join_day = join_date.day

            # If joined after 11th → deduct months up to and including that month
            if join_day > 11:
                months_to_deduct = join_month_index + 1
            else:
                months_to_deduct = join_month_index

            if months_to_deduct > 0:
                deduction_fraction = months_to_deduct / 3
                adjusted_leaves_for_quarter = periodically_earned_leave * (1 - deduction_fraction)

                # Adjust only the first quarter's allocation; keep others intact
                if periods_passed > 1:
                    leaves = adjusted_leaves_for_quarter + periodically_earned_leave * (periods_passed - 1)
                else:
                    leaves = adjusted_leaves_for_quarter

        return leaves

    def get_leaves_for_previous_leave_period(self, working_days: int):
        from real_group_hrms.utils import fetch_leaves_for_working_days, get_remaining_days_for_pro_rated

        # This method is used to calculate the leaves for previous year, based on the Indian Factory Act.
        # Which says employee can earned 1 leave per applicable days worked in the previous year.
        from_date = add_months(get_year_start(self.effective_from), -12)
        to_date = add_months(get_year_ending(self.effective_to), -12)
        new_leaves = fetch_leaves_for_working_days(
            self.employee,
            from_date,
            to_date,
            working_days,
        )
        days = get_remaining_days_for_pro_rated(self.employee, from_date, to_date, working_days)
        leaves = days / working_days
        new_leaves += leaves
        return adjust_value(new_leaves)


def get_pro_rata_period_end_date(consider_current_month):
    # for earned leave, pro-rata period ends on the last day of the month
    # pro rata period end date is different for different periods

    date = getdate(frappe.flags.current_date) or getdate()
    if consider_current_month:
        period_end_date = get_last_day(date)
    else:
        period_end_date = get_last_day(add_months(date, -1))

    return period_end_date


def calculate_periods_passed(current_date, from_date, periods_per_year, months_per_period, consider_current_period):
    periods_passed = 0

    from_period = (from_date.year * periods_per_year) + ((from_date.month - 1) // months_per_period)
    current_period = (current_date.year * periods_per_year) + ((current_date.month - 1) // months_per_period)

    periods_passed = current_period - from_period
    if consider_current_period:
        periods_passed += 1

    return periods_passed


def is_earned_leave_applicable_for_current_period(date_of_joining, allocate_on_day, earned_leave_frequency):
    date = getdate(frappe.flags.current_date) or getdate()
    # If the date of assignment creation is >= the leave type's "Allocate On" date,
    # then the current month should be considered
    # because the employee is already entitled for the leave of that month

    condition_map = {
        "Monthly": (
            (allocate_on_day == "Date of Joining" and date.day >= date_of_joining.day)
            or (allocate_on_day == "First Day" and date >= get_first_day(date))
            or (allocate_on_day == "Last Day" and date == get_last_day(date))
        ),
        "Quarterly": (allocate_on_day == "First Day" and date >= get_quarter_start(date))
        or (allocate_on_day == "Last Day" and date == get_quarter_ending(date)),
        "Half-Yearly": (allocate_on_day == "First Day" and date >= get_semester_start(date))
        or (allocate_on_day == "Last Day" and date == get_semester_end(date)),
        "Yearly": (
            (allocate_on_day == "First Day" and date >= get_year_start(date))
            or (allocate_on_day == "Last Day" and date == get_year_ending(date))
        ),
    }

    return condition_map.get(earned_leave_frequency)


def get_leave_type_details():
    leave_type_details = frappe._dict()
    leave_types = frappe.get_all(
        "Leave Type",
        fields=[
            "name",
            "is_lwp",
            "is_earned_leave",
            "is_compensatory",
            "allocate_on_day",
            "is_carry_forward",
            "expire_carry_forwarded_leaves_after_days",
            "earned_leave_frequency",
            "rounding",
            # Custom fields for Real Group
            "custom_calculate_based_on_working_days",
            "custom_number_of_working_days",
            "custom_avail_leave_in_next_calendar_year",
        ],
    )
    for d in leave_types:
        leave_type_details.setdefault(d.name, d)
    return leave_type_details


def get_semester_start(date):
    if date.month <= 6:
        return get_year_start(date)
    else:
        return add_months(get_year_start(date), 6)


def get_semester_end(date):
    if date.month > 6:
        return get_year_ending(date)
    else:
        return add_months(get_year_ending(date), -6)


def get_earned_leaves():
    return frappe.get_all(
        "Leave Type",
        fields=[
            "name",
            "max_leaves_allowed",
            "earned_leave_frequency",
            "rounding",
            "allocate_on_day",
        ],
        filters={"is_earned_leave": 1, "custom_calculate_based_on_working_days": 0},
    )
