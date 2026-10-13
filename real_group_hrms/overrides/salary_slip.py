import frappe
from frappe.utils import flt, getdate
from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip
from real_group_hrms.doc_events.salary_structure_assignment import ESIC_ABBR, ESIC_SALARY_COMPONENT


class SalarySlipOverride(SalarySlip):
    def validate(self):
        super().validate()
        self.set_total_deduction_with_loan()

    def calculate_net_pay(self):
        super().calculate_net_pay()

        if self.apply_esic_exit_date_continuation():
            self.set_net_pay()
            self.set_total_deduction_with_loan()

    def set_total_deduction_with_loan(self):
        total_loan_repayment = flt(self.get("total_loan_repayment"))
        if not total_loan_repayment:
            self.custom_total_deduction_with_loan = flt(self.total_deduction)
            return
        self.custom_total_deduction_with_loan = flt(self.total_deduction) + total_loan_repayment

    def apply_esic_exit_date_continuation(self):
        esic_row = self.get_esic_deduction_row()
        if esic_row and flt(esic_row.amount) > 0:
            return False

        salary_structure_assignment = self.get_active_salary_structure_assignment()
        esi_exit_date = salary_structure_assignment.get("custom_esi_exit_date")
        if not esi_exit_date or not self.end_date:
            return False

        if getdate(self.end_date) > getdate(esi_exit_date):
            return False

        esic_structure_row = self.get_esic_salary_structure_row()
        if not esic_structure_row:
            return False

        amount, default_amount = self.get_esic_continuation_amount(
            esic_structure_row,
            esi_exit_date,
        )
        if amount <= 0:
            return False

        if esic_row:
            if flt(esic_row.amount) == amount and flt(esic_row.default_amount) == default_amount:
                return False

            esic_row.amount = amount
            esic_row.default_amount = default_amount
        else:
            self.update_component_row(
                esic_structure_row,
                amount,
                "deductions",
                data=self.data,
                default_amount=default_amount,
                remove_if_zero_valued=False,
            )

        return True

    def get_active_salary_structure_assignment(self):
        if not hasattr(self, "_salary_structure_assignment"):
            self.set_salary_structure_assignment()

        return self._salary_structure_assignment

    def get_esic_deduction_row(self):
        for row in self.deductions:
            if row.salary_component == ESIC_SALARY_COMPONENT or row.abbr == ESIC_ABBR:
                return row

        return None

    def get_esic_salary_structure_row(self):
        if not getattr(self, "_salary_structure_doc", None):
            self._salary_structure_doc = frappe.get_cached_doc("Salary Structure", self.salary_structure)

        for row in self._salary_structure_doc.deductions:
            if row.salary_component == ESIC_SALARY_COMPONENT or row.abbr == ESIC_ABBR:
                return row

        return None

    def get_esic_continuation_amount(self, esic_structure_row, esi_exit_date):
        if not getattr(self, "data", None) or not getattr(self, "default_data", None):
            self.data, self.default_data = self.get_data_for_eval()

        data = self.get_esic_continuation_eval_data(self.data.copy(), esi_exit_date)
        default_data = self.get_esic_continuation_eval_data(
            self.default_data.copy(),
            esi_exit_date,
        )

        amount = flt(
            self.eval_condition_and_formula(esic_structure_row, data),
            esic_structure_row.precision("amount"),
        )
        default_amount = flt(
            self.eval_condition_and_formula(esic_structure_row, default_data),
            esic_structure_row.precision("amount"),
        )

        return amount, default_amount

    def get_esic_continuation_eval_data(self, data, esi_exit_date):
        esic_limit = flt(frappe.db.get_single_value("Real Group Settings", "esic_deduction_limit"))
        if esic_limit:
            data["custom_basic_pay"] = min(
                flt(data.get("custom_basic_pay")) or esic_limit,
                esic_limit,
            )

        data["custom_esi_exit_date"] = esi_exit_date
        data["end_date"] = self.end_date

        return data

    def calculate_lwp_ppl_and_absent_days_based_on_attendance(
        self,
        holidays,
        daily_wages_fraction_for_half_day,
        consider_marked_attendance_on_holidays,
    ):
        lwp, absent = super().calculate_lwp_ppl_and_absent_days_based_on_attendance(
            holidays=holidays,
            daily_wages_fraction_for_half_day=daily_wages_fraction_for_half_day,
            consider_marked_attendance_on_holidays=consider_marked_attendance_on_holidays,
        )

        leave_type_map = self.get_leave_type_map()
        attendance_details = self.get_employee_attendance(
            start_date=self.start_date, end_date=self.actual_end_date
        )

        extra_absent = 0.0
        absent_equivalent_for_half_day = 1 - daily_wages_fraction_for_half_day

        for attendance in attendance_details:
            if attendance.status != "Half Day" or not attendance.leave_type:
                continue

            # Leave types already counted under LWP/PPL in base logic should not be counted again.
            if attendance.leave_type in leave_type_map:
                continue

            if (
                not consider_marked_attendance_on_holidays
                and getdate(attendance.attendance_date) in holidays
            ):
                continue

            extra_absent += absent_equivalent_for_half_day

        return lwp, absent + extra_absent
