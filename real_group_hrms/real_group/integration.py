import json
import time
from datetime import datetime

import oracledb as cx_Oracle
import frappe
from frappe.utils import flt

from real_group_hrms.real_group.employee_map import (
    ACCOUNT_MAP,
    ATTENDANCE_BALANCE,
    BONUS_TRANSACTION,
    EMPLOYEE_MAP,
    SALARY_SLIP_SALARY_TRANS,
    UPDATE_USER_MAP,
    USER_MAP,
)


def _escape_oracle_string(value):
    return str(value).replace("'", "''")


# ----------------Oracle Connection


def oracle_connection(company):
    oracle_dtl = frappe.db.get_value(
        "Oracle Credentials",
        {"company": company},
        ["name", "host", "database", "username"],
        as_dict=1,
    )
    if oracle_dtl:
        oc = frappe.get_doc("Oracle Credentials", oracle_dtl.name)
        ORACLE_USER = oracle_dtl.username
        ORACLE_PASSWORD = oc.get_password("password")
        ORACLE_DSN = f"{oracle_dtl.host}/{oracle_dtl.database}"
        if not ORACLE_USER:
            frappe.throw("Oracle User Missing in Real Group Settings")

        if not ORACLE_PASSWORD:
            frappe.throw("Oracle Password Missing in Real Group Settings")

        if not ORACLE_DSN:
            frappe.throw("Oracle DNS Missing in Real Group Settings")

        last_error = None
        for _ in range(3):
            try:
                con = cx_Oracle.connect(
                    user=ORACLE_USER, password=ORACLE_PASSWORD, dsn=ORACLE_DSN
                )
                return con
            except cx_Oracle.DatabaseError as er:
                last_error = er
                time.sleep(0.5)

        if last_error:
            frappe.log_error(title="Oracle Connection Error", message=last_error)
            return None

        return None
        # frappe.throw('Oracle Connection Error:', str(er))
    else:
        frappe.log_error("Company not allowed to insert in ERP")
        return None


# #----------------Oracle Connection defualt

# def oracle_connection():

# 	try:
# 		con = cx_Oracle.connect()
# 		print(con.version)
# 		con.close()
# 	except Exception as e:
# 		print(e)

# ----------------Employee CRUD Operation


def create_employee(doc, method):
    con = oracle_connection(doc.company)
    if not con:
        frappe.log_error(title="Oracle Connection information is not set")
    else:
        try:
            cur = con.cursor()

            # -------------------------------------------------------Employee Creation CRUD
            check_emp_sql = f"""SELECT EMP_CODE FROM RIPLRR.EMP_MAST WHERE EMP_CODE = '{doc.name}'"""
            cur.execute(check_emp_sql)
            result = cur.fetchall()
            if result:
                sql = get_update_query(EMPLOYEE_MAP, "RIPLRR.EMP_MAST", doc.name)
                frappe.throw("Employee ID present in oracle, clean it first!!")
                frappe.log_error(title="update query for employee", message=sql)
                cur.execute(sql)

            else:
                sql = get_insert_query(EMPLOYEE_MAP, "RIPLRR.EMP_MAST", doc.name)
                frappe.log_error(title="Insert query for employee", message=sql)
                cur.execute(sql)

            # -------------------------------------------------------Account Creation CRUD

            check_acc_sql = f"""SELECT ACC_CODE FROM RIPLRR.ACC_MAST WHERE ACC_CODE = '{doc.name}'"""
            cur.execute(check_acc_sql)
            result = cur.fetchall()
            if result:
                frappe.throw("Account ID present in oracle, clean it first!!")
                sql = get_account_update_query(ACCOUNT_MAP, "RIPLRR.ACC_MAST", doc.name)
                cur.execute(sql)

            else:
                frappe.log_error(title="EMP_CODE", message="No result found")
                sql = get_account_insert_query(ACCOUNT_MAP, "RIPLRR.ACC_MAST", doc.name)
                cur.execute(sql)

            con.commit()  # -----------------Database commit value

        except cx_Oracle.DatabaseError as er:
            frappe.log_error(title="Oracle Query Error", message=er)
            frappe.throw(f"Oracle Query Error: {er!s}")
            con.rollback()

        except Exception as er:
            frappe.log_error(title="Oracle Exception", message=er)
            frappe.throw(f"Oracle Exception: {er!s}")
            con.rollback()

        finally:
            if cur:
                cur.close()

            if con:
                con.close()


def update_employee(doc, method):
    con = oracle_connection(doc.company)
    if not con:
        frappe.log_error(title="Oracle Connection information is not set")
    else:
        try:
            cur = con.cursor()

            safe_emp_code = _escape_oracle_string(doc.name)
            check_emp_sql = (
                "SELECT EMP_CODE FROM RIPLRR.EMP_MAST "
                f"WHERE TRIM(TO_CHAR(EMP_CODE)) = TRIM('{safe_emp_code}')"
            )
            cur.execute(check_emp_sql)
            result = cur.fetchall()
            if result:
                sql = get_update_query(EMPLOYEE_MAP, "RIPLRR.EMP_MAST", doc.name)
                if sql:
                    cur.execute(sql)

            else:
                sql = get_insert_query(EMPLOYEE_MAP, "RIPLRR.EMP_MAST", doc.name)
                cur.execute(sql)

            check_acc_code_sql = (
                "SELECT ACC_CODE FROM RIPLRR.ACC_MAST "
                f"WHERE TRIM(TO_CHAR(ACC_CODE)) = TRIM('{safe_emp_code}')"
            )
            cur.execute(check_acc_code_sql)
            result = cur.fetchall()
            if result:
                sql = get_account_update_query(ACCOUNT_MAP, "RIPLRR.ACC_MAST", doc.name)
                if sql:
                    cur.execute(sql)

            else:
                sql = get_account_insert_query(ACCOUNT_MAP, "RIPLRR.ACC_MAST", doc.name)
                cur.execute(sql)

            con.commit()  # -----------------Database commit value

        except cx_Oracle.DatabaseError as er:
            frappe.log_error(title="Oracle Query Error", message=er)
            frappe.throw(f"Oracle Query Error: {er!s}")
            con.rollback()

        except Exception as er:
            frappe.log_error(title="Oracle Exception", message=er)
            frappe.throw(f"Oracle Exception: {er!s}")
            con.rollback()

        finally:
            if cur:
                cur.close()
            if con:
                con.close()


def enqueue_update_employee(doc, method):
    if frappe.flags.in_migrate or frappe.flags.in_install or frappe.flags.in_patch:
        return

    frappe.enqueue(
        "real_group_hrms.real_group.integration.update_employee_by_name",
        queue="short",
        enqueue_after_commit=True,
        employee=doc.name,
    )


def update_employee_by_name(employee):
    doc = frappe.get_doc("Employee", employee)
    update_employee(doc, method=None)


def get_insert_query(map, table_name, employee_code):
    employee_values = frappe.db.sql(
        """
		SELECT
			name,
			employee_name,
			date_of_joining,
			(SELECT custom_erp_code FROM `tabDepartment` WHERE name = e.department  LIMIT 1) as department,
			grade,
			(SELECT custom_erp_code FROM `tabDesignation` WHERE name = e.designation  LIMIT 1) as designation,
			date_of_birth,
			custom_father_name,
			custom_mother_name,
			custom_off_days,
			(SELECT custom_erp_code FROM `tabCompany` WHERE name = e.company  LIMIT 1) as company,
			(SELECT erp_code FROM `tabDivision` WHERE name = e.custom_division  LIMIT 1) as custom_division,
			(SELECT custom_erp_code FROM `tabGender` WHERE name = e.gender LIMIT 1) as gender,
			(SELECT custom_erp_itax_category FROM `tabGender` WHERE name = e.gender LIMIT 1) as custom_itax_category,
			pan_number,
			passport_number,
			(SELECT custom_erp_code FROM `tabBank` WHERE name = e.bank_name LIMIT 1) as bank_name,
			bank_ac_no,
			custom_esic,
			reports_to,
			relieving_date,
			reason_for_leaving,
			modified,
			creation,
			default_shift,
			blood_group,
			ifsc_code,
			cell_number,
			LEFT(current_address, 50) AS current_address,
			custom_payroll_series,
			custom_aadhar_number,
			LEFT(permanent_address, 50) AS permanent_address,
			LEFT(custom_emergency_address, 50) AS custom_emergency_address,
			emergency_phone_number,
			person_to_be_contacted,
			custom_permanent_pin_code,
			custom_permanent_country,
			custom_current_country,
			custom_current_pin_code,
			date_of_retirement,
			date_of_joining,
			(SELECT username FROM `tabUser` WHERE name = e.owner) as user_id,
			(SELECT erp_code FROM `tabSalary Mode` WHERE name = e.salary_mode LIMIT 1) as salary_mode,
			(SELECT erp_code FROM `tabSkill Status` WHERE name = e.custom_skill_status LIMIT 1) as custom_skill_status,
			(SELECT erp_code FROM `tabReligion` WHERE name = e.custom_religion LIMIT 1) as custom_religion,
			(SELECT erp_code FROM `tabWage Basis` WHERE name = e.custom_wage_basis LIMIT 1) as custom_wage_basis,
			custom_permanent_city,
			custom_permanent_district,
			(SELECT erp_code FROM `tabState` WHERE name = e.custom_permanent_state LIMIT 1) as custom_permanent_state,
			custom_current_city,
			custom_current_district,
			(SELECT erp_code FROM `tabState` WHERE name = e.custom_current_state LIMIT 1) as custom_current_state,
			(SELECT erp_code FROM `tabEmployee Category` WHERE name = e.custom_emp_category LIMIT 1) as custom_emp_category,
			(SELECT erp_code FROM `tabPayroll Series` WHERE name = e.custom_payroll_series LIMIT 1) as custom_payroll_series
		FROM
			`tabEmployee` e
		WHERE
			name = %s
	""",
        (employee_code),
        as_dict=1,
    )

    if not employee_values:
        return None

    employee_values = employee_values[0]

    keys = []
    values = []

    sql = ""

    for key, value in map.items():
        if value:
            keys.append(key)
            value_to_insert = None
            if employee_values[value]:
                value_to_insert = employee_values[value]
            if value_to_insert is None:
                values.append("")
            else:
                if "date" in value:
                    values.append(f"TO_DATE('{value_to_insert}', 'YYYY-MM-DD')")
                elif "modified" in value:
                    value_to_insert = str(value_to_insert).split(".")
                    values.append(
                        f"TO_DATE('{value_to_insert[0]}', 'YYYY-MM-DD HH24:MI:SS')"
                    )
                else:
                    values.append(f"{value_to_insert}")

    sql = f"""
		INSERT INTO {table_name}
			({",".join([str(elem) for elem in keys])})
		VALUES
			({",".join([str(elem) if "TO_DATE" in str(elem) else "'" + str(elem) + "'" for elem in values])})
	"""

    return sql


def get_update_query(map, table_name, employee_code):
    employee_values = frappe.db.sql(
        """
		SELECT
			name,
			employee_name,
			date_of_joining,
			(SELECT custom_erp_code FROM `tabDepartment` WHERE name = e.department  LIMIT 1) as department,
			grade,
			(SELECT custom_erp_code FROM `tabDesignation` WHERE name = e.designation  LIMIT 1) as designation,
			date_of_birth,
			custom_father_name,
			custom_mother_name,
			custom_off_days,
			(SELECT custom_erp_code FROM `tabCompany` WHERE name = e.company  LIMIT 1) as company,
			(SELECT erp_code FROM `tabDivision` WHERE name = e.custom_division  LIMIT 1) as custom_division,
			(SELECT custom_erp_code FROM `tabGender` WHERE name = e.gender LIMIT 1) as gender,
			(SELECT custom_erp_itax_category FROM `tabGender` WHERE name = e.gender LIMIT 1) as custom_itax_category,
			pan_number,
			passport_number,
			(SELECT custom_erp_code FROM `tabBank` WHERE name = e.bank_name LIMIT 1) as bank_name,
			bank_ac_no,
			LEFT(current_address, 50) AS current_address,
			custom_esic,
			reports_to,
			relieving_date,
			reason_for_leaving,
			modified,
			creation,
			default_shift,
			blood_group,
			ifsc_code,
			cell_number,
			custom_payroll_series,
			custom_aadhar_number,
			LEFT(permanent_address, 50) AS permanent_address,
			LEFT(custom_emergency_address, 50) AS custom_emergency_address,
			emergency_phone_number,
			person_to_be_contacted,
			custom_permanent_pin_code,
			custom_permanent_country,
			custom_current_country,
			custom_current_pin_code,
			date_of_retirement,
			date_of_joining,
			(SELECT username FROM `tabUser` WHERE name = e.owner) as user_id,
			(SELECT erp_code FROM `tabSalary Mode` WHERE name = e.salary_mode LIMIT 1) as salary_mode,
			(SELECT erp_code FROM `tabSkill Status` WHERE name = e.custom_skill_status LIMIT 1) as custom_skill_status,
			(SELECT erp_code FROM `tabReligion` WHERE name = e.custom_religion LIMIT 1) as custom_religion,
			(SELECT erp_code FROM `tabWage Basis` WHERE name = e.custom_wage_basis LIMIT 1) as custom_wage_basis,
			custom_permanent_city,
			custom_permanent_district,
			(SELECT erp_code FROM `tabState` WHERE name = e.custom_permanent_state LIMIT 1) as custom_permanent_state,
			custom_current_city,
			custom_current_district,
			(SELECT erp_code FROM `tabState` WHERE name = e.custom_current_state LIMIT 1) as custom_current_state,
			(SELECT erp_code FROM `tabEmployee Category` WHERE name = e.custom_emp_category LIMIT 1) as custom_emp_category,
			(SELECT erp_code FROM `tabPayroll Series` WHERE name = e.custom_payroll_series LIMIT 1) as custom_payroll_series
		FROM
			`tabEmployee` e
		WHERE
			name = %s
	""",
        (employee_code),
        as_dict=True,
    )

    if not employee_values:
        return None

    employee_values = employee_values[0]

    set_clauses = []

    for key, value in map.items():
        if not value or value == "name":
            continue

        value_to_update = employee_values.get(value)
        if value_to_update is None or value_to_update == "":
            set_clauses.append(f"{key} = NULL")
            continue

        if "modified" in value:
            value_to_update = _escape_oracle_string(str(value_to_update).split(".")[0])
            set_clauses.append(
                f"{key} = TO_DATE('{value_to_update}', 'YYYY-MM-DD HH24:MI:SS')"
            )
        elif "date" in value:
            value_to_update = _escape_oracle_string(str(value_to_update).split(" ")[0])
            set_clauses.append(f"{key} = TO_DATE('{value_to_update}', 'YYYY-MM-DD')")
        else:
            value_to_update = _escape_oracle_string(value_to_update)
            set_clauses.append(f"{key} = '{value_to_update}'")

    if not set_clauses:
        return None

    safe_emp_code = _escape_oracle_string(employee_code)

    sql = f"""
		UPDATE {table_name}
		SET
			{", ".join(set_clauses)}
		WHERE
			TRIM(TO_CHAR(EMP_CODE)) = TRIM('{safe_emp_code}')
	"""

    return sql


# -------------------------Account CRUD Operation Query


def get_account_insert_query(map, table_name, employee_code):
    employee_values = frappe.db.sql(
        """
		SELECT
			name,
			employee_name,
			(SELECT username FROM `tabUser` WHERE name = modified_by LIMIT 1) as user_id,
			(SELECT custom_erp_code FROM `tabCompany` WHERE name = company  LIMIT 1) as company,
			(SELECT erp_acc_type FROM `tabPayroll Series` WHERE name = custom_payroll_series LIMIT 1) as acc_type,
			(SELECT erp_acc_schedule FROM `tabPayroll Series` WHERE name = custom_payroll_series LIMIT 1) as acc_sch

		FROM
			`tabEmployee`
		WHERE
			name = %s
	""",
        (employee_code),
        as_dict=1,
    )

    # temp Syntex for user id
    # (SELECT name FROM `tabUser` WHERE name = owner) as user_id

    if not employee_values:
        return None

    employee_values = employee_values[0]

    keys = []
    values = []
    for key, value in map.items():
        if value:
            keys.append(key)
            value_to_insert = employee_values[value]
            if value_to_insert is None:
                values.append("")
            else:
                values.append(f"{value_to_insert}")

    sql = f"""
		INSERT INTO {table_name}
			({",".join([str(elem) for elem in keys])})
		VALUES
			({",".join([str(elem) if "TO_DATE" in str(elem) else "'" + str(elem) + "'" for elem in values])})
	"""
    # frappe.log_error(title="Query_Bulding_Syntex", message=sql)

    return sql


def get_account_update_query(map, table_name, employee_code):
    employee_values = frappe.db.sql(
        """
		SELECT
			name,
			employee_name,
			(SELECT username FROM `tabUser` WHERE name = modified_by LIMIT 1) as user_id,
			(SELECT custom_erp_code FROM `tabCompany` WHERE name = company  LIMIT 1) as company,
			(SELECT erp_acc_type FROM `tabPayroll Series` WHERE name = custom_payroll_series LIMIT 1) as acc_type,
			(SELECT erp_acc_schedule FROM `tabPayroll Series` WHERE name = custom_payroll_series LIMIT 1) as acc_sch
		FROM
			`tabEmployee`
		WHERE
			name = %s
	""",
        (employee_code),
        as_dict=True,
    )

    if not employee_values:
        return None

    employee_values = employee_values[0]

    set_clauses = []

    for key, value in map.items():
        if not value or value == "name":
            continue

        value_to_update = employee_values.get(value)
        if value_to_update is None or value_to_update == "":
            set_clauses.append(f"{key} = NULL")
        else:
            value_to_update = _escape_oracle_string(value_to_update)
            set_clauses.append(f"{key} = '{value_to_update}'")

    if not set_clauses:
        return None

    safe_emp_code = _escape_oracle_string(employee_code)

    sql = f"""
		UPDATE {table_name}
		SET
			{", ".join(set_clauses)}
		WHERE
			TRIM(TO_CHAR(ACC_CODE)) = TRIM('{safe_emp_code}')
	"""

    return sql


# ----------------USER CRUD Operation


def create_user(doc, method):
    if frappe.db.exists("Employee", doc.username):
        company = frappe.db.get_value("Employee", doc.username, "company")
    else:
        return

    con = oracle_connection(company)
    if not con:
        frappe.log_error(title="Oracle Connection information is not set")
    else:
        try:
            cur = con.cursor()

            branch = frappe.db.get_value("Employee", doc.username, "branch")
            user_perm = frappe.get_doc(
                dict(
                    doctype="User Permission",
                    user=doc.username,
                    allow="Branch",
                    for_value=branch,
                )
            )
            user_perm.insert(ignore_permissions=True)
            user_perm.save(ignore_permissions=True)

            check_emp_sql = f"""SELECT USER_CODE FROM RIPLRR.USER_MAST WHERE USER_CODE = '{doc.name}'"""
            cur.execute(check_emp_sql)
            result = cur.fetchall()
            today = doc.creation.split(" ")[0]
            if result:
                # frappe.throw(f"User ID {emp_code} present in oracle, clean it first!!")
                sql = get_user_update_query(
                    UPDATE_USER_MAP, "RIPLRR.USER_MAST", doc.name, today
                )
                frappe.log_error(title="User Update Query", message=sql)
                cur.execute(sql)

            else:
                sql = get_user_insert_query(
                    USER_MAP, "RIPLRR.USER_MAST", doc.name, today
                )

                cur.execute(sql)
            con.commit()  # -----------------Database commit value

        except cx_Oracle.DatabaseError as er:
            frappe.log_error(title="Oracle Query Error", message=er)
            frappe.throw(f"Oracle Query Error: {er!s}")
            con.rollback()

        except Exception as er:
            frappe.log_error(title="Oracle Exception", message=er)
            frappe.throw(f"Oracle Exception:{er!s}")
            con.rollback()

        finally:
            if cur:
                cur.close()
            if con:
                con.close()


def update_user(doc, method):
    if frappe.db.exists("Employee", doc.username):
        company = frappe.db.get_value("Employee", doc.username, "company")
    else:
        return

    con = oracle_connection(company)
    if not con:
        frappe.log_error(title="Oracle Connection information is not set")
    else:
        try:
            cur = con.cursor()

            check_emp_sql = f"""SELECT USER_CODE FROM RIPLRR.USER_MAST WHERE USER_CODE = '{doc.name}'"""
            cur.execute(check_emp_sql)
            result = cur.fetchall()
            today = str(doc.creation).split(" ")[0]
            if result:
                sql = get_user_update_query(
                    UPDATE_USER_MAP, "RIPLRR.USER_MAST", doc.name, today
                )
                cur.execute(sql)

            else:
                sql = get_user_insert_query(
                    USER_MAP, "RIPLRR.USER_MAST", doc.name, today
                )
                cur.execute(sql)

            con.commit()  # -----------------Database commit value

        except cx_Oracle.DatabaseError as er:
            frappe.log_error(title="Oracle Query Error", message=er)
            frappe.throw(f"Oracle Query Error: {er!s}")
            con.rollback()

        except Exception as er:
            frappe.log_error(title="Oracle Exception", message=er)
            frappe.throw(f"Oracle Exception: {er!s}")
            con.rollback()

        finally:
            if cur:
                cur.close()
            if con:
                con.close()


def get_user_insert_query(map, table_name, user_code, today):
    user_default_pass = f"{user_code}@123"

    # today = doc.creation.split(' ')[0]

    fy = frappe.db.sql(
        f"SELECT name FROM `tabFiscal Year` WHERE '{today}' BETWEEN year_start_date AND year_end_date",
        as_dict=1,
    )
    # frappe.throw(str(fy))
    if fy:
        fiscal_year = fy[0].name[2:4]
    else:
        frappe.throw("Fiscal Year Not defined for the Today Date")

    user_values = frappe.db.sql(
        """
		SELECT
			u.name as name,
			u.full_name as full_name,
			%s as password,
			9 as user_level,
			%s as acc_year,
			CASE
				WHEN u.enabled = 0 THEN 'L'
				ELSE ''
			END as user_status,
			(SELECT custom_erp_code FROM `tabDepartment` WHERE name = e.department  LIMIT 1) as department,
			(SELECT custom_erp_code FROM `tabCompany` WHERE name = e.company  LIMIT 1) as company,
			(SELECT erp_code FROM `tabDivision` WHERE name = e.custom_division  LIMIT 1) as custom_division,
			e.name as emp_code,
			90 as passwd_reset_days,
			(SELECT username FROM `tabUser` WHERE name = u.owner LIMIT 1) as created_by,
			u.creation,
			u.modified
		FROM
			`tabUser` u
		LEFT JOIN
			`tabEmployee` e ON e.name = u.name
		WHERE
			u.name = %s
	""",
        (user_default_pass, fiscal_year, user_code),
        as_dict=1,
    )

    if not user_values:
        return None

    user_values = user_values[0]

    keys = []
    values = []
    for key, value in map.items():
        if value:
            keys.append(key)
            value_to_insert = user_values[value]
            if value_to_insert is None:
                values.append("")
            else:
                if "creation" in value:
                    value_to_insert = str(value_to_insert).split(".")
                    values.append(
                        f"TO_DATE('{value_to_insert[0]}', 'YYYY-MM-DD HH24:MI:SS')"
                    )
                elif "modified" in value:
                    value_to_insert = str(value_to_insert).split(".")
                    values.append(
                        f"TO_DATE('{value_to_insert[0]}', 'YYYY-MM-DD HH24:MI:SS')"
                    )
                elif "password" in value:
                    values.append(
                        f"(SELECT RIPLRR.LHS_UTILITY.GET_ENCRYPT('{value_to_insert}') FROM DUAL)"
                    )
                else:
                    values.append(f"{value_to_insert}")

    formatted_values = []
    for elem in values:
        elem_str = str(elem)
        if "TO_DATE" in elem_str:
            formatted_values.append(elem_str)
        elif "SELECT" in elem_str:
            formatted_values.append(elem)
        elif "passwd_reset_days" in elem_str or "user_level" in elem_str:
            formatted_values.append(int(elem))
        else:
            formatted_values.append("'" + elem_str + "'")

    sql = f"""
		INSERT INTO {table_name}
			({",".join([str(elem) for elem in keys])})
		VALUES
			({",".join(formatted_values)})
	"""

    return sql


def get_user_update_query(map, table_name, user_code, today):
    password = frappe.db.get_single_value("Virtual Password", "virtual_pass")
    # frappe.throw(str(user_pass))
    if password:
        user_pass = password

        fy = frappe.db.sql(
            f"SELECT name FROM `tabFiscal Year` WHERE '{today}' BETWEEN year_start_date AND year_end_date",
            as_dict=1,
        )

        reset_days = frappe.db.get_value(
            "System Settings", "System Settings", "force_user_to_reset_password"
        )

        user_values = frappe.db.sql(
            """
			SELECT
				u.full_name as full_name,
				%s as password,
				CASE
					WHEN u.enabled = 0 THEN 'L'
					ELSE ''
				END as user_status,
				CASE
					WHEN u.enabled = 0 THEN u.modified
					ELSE ''
				END as close_date,
				(SELECT custom_erp_code FROM `tabDepartment` WHERE name = e.department  LIMIT 1) as department,
				e.name as emp_code,
				%s as passwd_reset_days,
				u.modified,
				e.reports_to as reporting_to_user_code
			FROM
				`tabUser` u
			LEFT JOIN
				`tabEmployee` e ON e.name = u.name
			WHERE
				u.name = %s
		""",
            (user_pass, reset_days, user_code),
            as_dict=True,
        )

        if not user_values:
            return None

        frappe.db.set_value("Virtual Password", "Virtual Password", "virtual_pass", "")

        user_values = user_values[0]

        set_clauses = []

        for key, value in map.items():
            if value:
                value_to_update = user_values[value]
                if value_to_update is None:
                    set_clauses.append(f"{key} = ''")

                elif value_to_update == "name":
                    continue

                elif "password" in str(value):
                    set_clauses.append(
                        f"{key} = (SELECT RIPLRR.LHS_UTILITY.GET_ENCRYPT('{value_to_update}') FROM DUAL)"
                    )

                elif "TO_DATE" in str(value):
                    set_clauses.append(f"{key} = {value_to_update}")

                elif "passwd_reset_days" in str(value):
                    set_clauses.append(f"{key} = {int(value_to_update)}")

                elif (
                    isinstance(value, str)
                    and "DATE" in key.upper()
                    and value_to_update != ""
                ):
                    set_clauses.append(f"{key} = TIMESTAMP '{value_to_update}'")

                else:
                    set_clauses.append(f"{key} = '{value_to_update}'")

        sql = f"""
			UPDATE {table_name}
			SET
				{", ".join(set_clauses)}
			WHERE
				USER_CODE = '{user_code}'
		"""

        return sql

    else:
        user_pass = "unidentified"

        fy = frappe.db.sql(
            f"SELECT name FROM `tabFiscal Year` WHERE '{today}' BETWEEN year_start_date AND year_end_date",
            as_dict=1,
        )

        if not fy:
            frappe.throw("Fiscal Year Not defined for the Today Date")

        reset_days = frappe.db.get_value(
            "System Settings", "System Settings", "force_user_to_reset_password"
        )

        user_values = frappe.db.sql(
            """
			SELECT
				u.full_name as full_name,
				%s as password,
				CASE
					WHEN u.enabled = 0 THEN 'L'
					ELSE ''
				END as user_status,
				CASE
					WHEN u.enabled = 0 THEN u.modified
					ELSE ''
				END as close_date,
				(SELECT custom_erp_code FROM `tabDepartment` WHERE name = e.department  LIMIT 1) as department,
				e.name as emp_code,
				%s as passwd_reset_days,
				u.modified,
				e.reports_to as reporting_to_user_code
			FROM
				`tabUser` u
			LEFT JOIN
				`tabEmployee` e ON e.name = u.name
			WHERE
				u.name = %s
		""",
            (user_pass, reset_days, user_code),
            as_dict=True,
        )

        if not user_values:
            return None

        frappe.db.set_value("Virtual Password", "Virtual Password", "virtual_pass", "")

        user_values = user_values[0]

        set_clauses = []

        for key, value in map.items():
            if value:
                value_to_update = user_values[value]
                if value_to_update is None:
                    set_clauses.append(f"{key} = ''")

                elif value_to_update == "name":
                    continue

                elif "password" in str(value):
                    continue

                elif "TO_DATE" in str(value):
                    set_clauses.append(f"{key} = {value_to_update}")

                elif "passwd_reset_days" in str(value):
                    set_clauses.append(f"{key} = {int(value_to_update)}")

                elif (
                    isinstance(value, str)
                    and "DATE" in key.upper()
                    and value_to_update != ""
                ):
                    set_clauses.append(f"{key} = TIMESTAMP '{value_to_update}'")

                else:
                    set_clauses.append(f"{key} = '{value_to_update}'")

        sql = f"""
			UPDATE {table_name}
			SET
				{", ".join(set_clauses)}
			WHERE
				USER_CODE = '{user_code}'
		"""

        return sql


# ----------------Salary Slip CRUD Operation

# ERP REFRENCE ---------> SALARY TRANSACTION(RIPLRR.EMP_SAL_TRAN)  = SALARY SLIP


def create_salary_slip(doc, method):
    # Skip ERP posting for companies that are not configured for Oracle integration.
    oracle_dtl = frappe.db.get_value(
        "Oracle Credentials", {"company": doc.company}, "name"
    )
    if not oracle_dtl:
        return

    con = oracle_connection(doc.company)
    if not con:
        frappe.log_error(
            title="Oracle Connection information is not set",
            message=f"Salary Slip: {doc.name}, Company: {doc.company}, Employee: {doc.employee}",
        )
        frappe.throw(
            f"Oracle connection failed for company '{doc.company}'. Salary Slip not posted to ERP."
        )
    else:
        try:
            cur = con.cursor()

            # Get Salary Slip Insert SQL
            sql_dict = get_salary_slip_insert_query(
                SALARY_SLIP_SALARY_TRANS,
                "RIPLRR.EMP_SAL_TRAN",
                doc.name,
                doc.salary_structure,
            )
            if not sql_dict or not sql_dict.get("sql_queries"):
                frappe.throw(
                    f"No salary transaction rows prepared for Salary Slip {doc.name}."
                )

            sql_list = sql_dict.get("sql_queries")
            emp_code = sql_dict.get("emp_code")
            cal_year = sql_dict.get("cal_year")
            month = sql_dict.get("month")

            # Check for the same month salary slip if exist
            check_for_existing_record_sql = f"SELECT * FROM RIPLRR.EMP_SAL_TRAN WHERE EMP_CODE = '{emp_code}' AND CAL_YEAR = '{cal_year}' AND MONTH = '{month}'"
            # frappe.log_error("check_for_existing_record_sql", check_for_existing_record_sql)
            cur.execute(check_for_existing_record_sql)
            result_for_existing = cur.fetchall()
            if (
                result_for_existing
            ):  # if salary slip exist then check is already trasaction done on erp
                check_for_transaction_sql = f"SELECT * FROM RIPLRR.EMP_SAL_TRAN WHERE EMP_CODE = '{emp_code}' AND CAL_YEAR = '{cal_year}' AND MONTH = '{month}' AND (ACC_VRNO IS NOT NULL OR ACC_TCODE IS NOT NULL OR PAYMENT_VRNO IS NOT NULL OR PAYMENT_TCODE IS NOT NULL)"
                cur.execute(check_for_transaction_sql)
                result_for_transaction = cur.fetchall()

                if result_for_transaction:  # if exist then throw msg
                    frappe.throw(
                        f"Salary Transaction Already Exist For Employee - '{emp_code}' AND Month - '{month}' And Transaction Completed!!"
                    )

                else:  # else update the salary transaction
                    if doc.custom_bonus_amount != 0:
                        # series = get_next_series_no(doc.doctype, doc.company, doc.posting_date, cur)
                        # frappe.log_error("next Series",str(series))
                        check_acc_vrno = f"""
											SELECT VRNO FROM RIPLRR.EMP_BONUS_TRAN
											WHERE EMP_CODE = '{doc.employee}'
												AND FROM_DATE = TO_DATE('{doc.start_date} 00:00:00', 'YYYY-MM-DD HH24:MI:SS')
												AND TO_DATE = TO_DATE('{doc.end_date} 00:00:00', 'YYYY-MM-DD HH24:MI:SS')
												AND ACC_VRNO IS NULL
											"""
                        # frappe.throw(str(check_acc_vrno))
                        cur.execute(check_acc_vrno)
                        vrno = cur.fetchall()
                        series = ""
                        if vrno:
                            # frappe.throw(str(vrno[0][0]))
                            series = vrno[0][0]
                        else:
                            frappe.throw("Please remove bonus account posting from ERP")

                        # frappe.throw(f"Series - {str(series)}")

                        bonus_tran_update_dict = get_bonus_transaction_update_query(
                            BONUS_TRANSACTION, "RIPLRR.EMP_BONUS_TRAN", doc.name, series
                        )
                        bonus_tran_update_sql = bonus_tran_update_dict.get("sql_query")

                        # frappe.throw(str(bonus_tran_update_sql))
                        if bonus_tran_update_sql is not None:
                            cur.execute(bonus_tran_update_sql)
                            frappe.db.set_value(
                                "Salary Slip", doc.name, "custom_erp_vrno", series
                            )

                    attend_bal_sql_update_dict = get_attendance_balance_update_query(
                        ATTENDANCE_BALANCE, "RIPLRR.EMP_ATTEND_BAL", doc.name
                    )
                    attend_bal_sql_update_list = (attend_bal_sql_update_dict or {}).get(
                        "sql_queries"
                    ) or []

                    for attend_bal_sql in attend_bal_sql_update_list:
                        cur.execute(attend_bal_sql)

                    sql_update_dict = get_salary_slip_update_query(
                        SALARY_SLIP_SALARY_TRANS,
                        "RIPLRR.EMP_SAL_TRAN",
                        doc.name,
                        doc.salary_structure,
                    )
                    sql_update_list = (sql_update_dict or {}).get("sql_queries") or []

                    for sql in sql_update_list:
                        cur.execute(sql)

            else:  # else direct insert new salary slip
                bonus_tran = ""
                if doc.custom_bonus_amount != 0:
                    series = get_next_series_no(
                        doc.doctype, doc.company, doc.posting_date, con, cur
                    )

                    frappe.db.set_value(
                        "Salary Slip", doc.name, "custom_erp_vrno", series
                    )

                    # Get BONUS TRANSACION Insert SQL
                    bonus_tran_query = get_bonus_transaction_insert_query(
                        BONUS_TRANSACTION, "RIPLRR.EMP_BONUS_TRAN", doc.name, series
                    )
                    bonus_tran = bonus_tran_query.get("sql_query")

                # Get Attend Bal Insert SQL
                attend_bal_queries = get_attendance_balance_insert_query(
                    ATTENDANCE_BALANCE, "RIPLRR.EMP_ATTEND_BAL", doc.name
                )
                attend_sql_list = (attend_bal_queries or {}).get("sql_queries") or []

                if bonus_tran != "":
                    cur.execute(bonus_tran)

                for attend_sql in attend_sql_list:
                    cur.execute(attend_sql)

                for sql in sql_list:
                    cur.execute(sql)

            con.commit()  # -----------------Database commit value

        except cx_Oracle.DatabaseError as er:
            frappe.log_error(title="Oracle Query Error", message=er)
            frappe.throw(f"Oracle Query Error: {er!s}")
            con.rollback()

        except Exception as er:
            frappe.log_error(title="Oracle Exception", message=f"{er}\n{sql_dict}")
            frappe.throw(f"Oracle Exception: {er!s}")
            con.rollback()

        finally:
            if cur:
                cur.close()

            if con:
                con.close()


def cancel_salary_slip(doc, method):
    con = oracle_connection(doc.company)
    if not con:
        frappe.log_error(title="Oracle Connection information is not set")
    else:
        try:
            cur = con.cursor()

            # Get Salary Slip Insert 0 on Cancel
            salary_slip = frappe.db.sql(
                """
					SELECT
						employee AS emp_code,
						EXTRACT(YEAR FROM ss.end_date) AS custom_calendar_year,
						UPPER(TRIM(TO_CHAR(ss.end_date, 'MON'))) AS custom_month,
						ss.modified,
						ss.posting_date,
						ss.custom_erp_vrno
					FROM
						`tabSalary Slip` as ss
					WHERE
						ss.name = %s
					""",
                (doc.name),
                as_dict=1,
            )

            emp_code = salary_slip[0].get("emp_code")
            cal_year = salary_slip[0].get("custom_calendar_year")
            month = salary_slip[0].get("custom_month")
            lastupdate = str(salary_slip[0].get("modified")).split(".")
            amount = 0.0

            vrno = salary_slip[0].get("custom_erp_vrno")

            update_zero_sql_salary_slip = f"""
					UPDATE
						RIPLRR.EMP_SAL_TRAN
					SET
						AFRATE = {amount},
						AFIELD = {amount},
						ACTUALS = {amount},
						LASTUPDATE = TO_DATE('{lastupdate[0]}', 'YYYY-MM-DD HH24:MI:SS')
					WHERE
						EMP_CODE = '{emp_code}'
						AND CAL_YEAR = '{cal_year}'
						AND MONTH = '{month}'
				"""

            update_zero_sql_attend_bal = f"""
					UPDATE
						RIPLRR.EMP_ATTEND_BAL
					SET
						DAYS = '0.0',
						LASTUPDATE = TO_DATE('{lastupdate[0]}', 'YYYY-MM-DD HH24:MI:SS')
					WHERE
						EMP_CODE = '{emp_code}'
						AND CAL_YEAR = '{cal_year}'
						AND MONTH = '{month}'
				"""

            update_zero_sql_bonus_tran = f"""
					UPDATE
						RIPLRR.EMP_BONUS_TRAN
					SET
						BONUS_AMT = '0.0'
					WHERE
						EMP_CODE = '{emp_code}'
						AND VRNO = '{vrno}'
				"""

            # Check for the same month salary slip if exist
            check_for_existing_record_sql = f"SELECT * FROM RIPLRR.EMP_SAL_TRAN WHERE EMP_CODE = '{emp_code}' AND CAL_YEAR = '{cal_year}' AND MONTH = '{month}'"

            cur.execute(check_for_existing_record_sql)
            result_for_existing = cur.fetchall()

            if (
                result_for_existing
            ):  # if salary slip exist then check is already trasaction done on erp
                check_for_transaction_sql = f"SELECT * FROM RIPLRR.EMP_SAL_TRAN WHERE EMP_CODE = '{emp_code}' AND CAL_YEAR = '{cal_year}' AND MONTH = '{month}' AND (ACC_VRNO IS NOT NULL OR ACC_TCODE IS NOT NULL OR PAYMENT_VRNO IS NOT NULL OR PAYMENT_TCODE IS NOT NULL)"
                cur.execute(check_for_transaction_sql)
                result_for_transaction = cur.fetchall()

                if result_for_transaction:  # if exist then throw msg
                    frappe.throw(
                        f"Salary Transaction Already Exist For Employee - {emp_code} AND Month - {month} And Transaction Completed!!"
                    )

                else:  # else update the salary transaction
                    cur.execute(update_zero_sql_attend_bal)
                    cur.execute(update_zero_sql_salary_slip)
                    cur.execute(update_zero_sql_bonus_tran)

            else:  # else direct insert new salary slip
                frappe.log_error(
                    "Salary Slip on cancel", "Salary Slip Not Found in ERP System"
                )

            con.commit()  # -----------------Database commit value

        except cx_Oracle.DatabaseError as er:
            frappe.log_error(title="Oracle Query Error", message=er)
            frappe.throw(f"Oracle Query Error: {er!s}")
            con.rollback()

        except Exception as er:
            frappe.log_error(title="Oracle Exception", message=er)
            frappe.throw(f"Oracle Exception: {er!s}")
            con.rollback()

        finally:
            if cur:
                cur.close()

            if con:
                con.close()


# ERP 'Loan' component code (Salary Component "Loan" -> custom_erp_code = 'LOAN').
LOAN_AFCODE = "LOAN"


def _get_lending_loan_repayment(docname):
    """Return the total loan repayment captured by the Lending app for this Salary Slip.

    The Lending app stores its repayment in the Salary Slip `loans` child table and
    exposes the slip-level sum as `total_loan_repayment`. This amount is NOT part of the
    slip `deductions` table, so the ERP salary transaction query never sees it. We read it
    here so it can be merged into the ERP 'Loan' component (AFCODE = 'LOAN') alongside any
    Additional Salary based 'Loan' deduction.
    """
    if "lending" not in frappe.get_installed_apps():
        return 0
    return flt(frappe.db.get_value("Salary Slip", docname, "total_loan_repayment"))


def _merge_lending_loan_into_erp_rows(salary_slips, docname):
    """Add the Lending app loan repayment onto the ERP 'Loan' row's AFIELD.

    AFIELD (= SUM of the slip's actual 'Loan' deduction amounts) is the field that carries
    the real deducted loan amount to Oracle; AFRATE/ACTUALS are 0/NULL for the Loan row.
    A single 'Loan' row in EMP_SAL_TRAN should therefore reflect both the Additional Salary
    'Loan' installment and the Lending app repayment.
    """
    lending_loan_repayment = _get_lending_loan_repayment(docname)
    if not lending_loan_repayment:
        return

    loan_row = next(
        (item for item in salary_slips if item.get("afcode") == LOAN_AFCODE), None
    )
    if loan_row:
        loan_row["afield"] = flt(loan_row.get("afield")) + lending_loan_repayment
    else:
        # No 'Loan' component in this employee's salary structure: there is no ERP row to
        # carry the lending repayment. Surface it instead of silently dropping the amount.
        frappe.log_error(
            title="ERP Loan sync: no 'Loan' component row",
            message=(
                f"Salary Slip {docname} has a Lending app loan repayment of "
                f"{lending_loan_repayment} but no 'Loan' (AFCODE='{LOAN_AFCODE}') component "
                f"in its salary structure, so the lending repayment was NOT sent to ERP."
            ),
        )


def get_salary_slip_insert_query(map, table_name, docname, doc_salary_structure):
    salary_slips = frappe.db.sql(
        """
		SELECT
			employee AS emp_code,
			ss.start_date AS from_date,
			EXTRACT(YEAR FROM ss.start_date) AS custom_calendar_year,
			UPPER(TRIM(TO_CHAR(ss.start_date, 'MON'))) AS custom_month,
			ss.modified,
			sd.parentfield,
			CASE 
				WHEN sd.parentfield = 'earnings' THEN CONCAT('E', sd.idx)
				WHEN sd.parentfield = 'deductions' THEN CONCAT('D', sd.idx)
				ELSE sd.idx
			END AS afno,
			(SELECT custom_erp_code FROM `tabSalary Component` WHERE name = sd.salary_component LIMIT 1) AS afcode,
			LEFT(UPPER(sd.salary_component), 15) AS afhead,
			CASE 
				WHEN sd.custom_erp_rate_indicator = 'D' AND sd.salary_component = 'Labour Welfare Fund' THEN ss_sd.amount
				WHEN sd.custom_erp_rate_indicator IN ('L', 'D', 'R') AND sd.salary_component != 'Labour Welfare Fund' THEN sd.amount
				WHEN sd.custom_erp_rate_indicator IN ('P', 'Q', 'C', 'F') THEN sd.custom_erp_rate
			END AS afrate,
			'rate_identifier' AS afratei,
			(SELECT custom_erp_code FROM `tabCompany` WHERE name = ss.company LIMIT 1) AS entity_code,
			(SELECT erp_code FROM `tabDivision` WHERE name = ss.custom_division LIMIT 1) AS custom_division,
			(SELECT erp_code FROM `tabEmployee Category` WHERE name = ss.custom_employee_category LIMIT 1) AS custom_emp_category,
			(SELECT erp_code FROM `tabPayroll Series` WHERE name = ss.custom_payroll_series LIMIT 1) AS custom_payroll_series,
			(SELECT username FROM `tabUser` WHERE name = ss.owner) AS user_code,
			IFNULL(SUM(ss_sd.amount), 0) AS afield,
			-- sd.amount AS actuals,
			CASE 
				WHEN sd.custom_erp_rate_indicator = 'D' AND sd.salary_component = 'Labour Welfare Fund' THEN ss_sd.amount
				WHEN sd.custom_erp_rate_indicator IN ('L', 'D', 'R') AND sd.salary_component != 'Labour Welfare Fund' THEN sd.amount
				WHEN sd.custom_erp_rate_indicator IN ('P', 'Q', 'C', 'F') THEN ss_sd.amount
			END AS actuals
		FROM
			`tabSalary Slip` AS ss
		LEFT JOIN
			`tabSalary Detail` AS sd ON sd.parent = ss.salary_structure
		LEFT JOIN
			`tabSalary Detail` AS ss_sd ON ss_sd.parent = ss.name AND (SELECT custom_erp_code FROM `tabSalary Component` WHERE name = ss_sd.salary_component LIMIT 1) = (SELECT custom_erp_code FROM `tabSalary Component` WHERE name = sd.salary_component LIMIT 1)
		WHERE
			ss.name = %s
		GROUP BY
			employee, ss.start_date, custom_calendar_year, custom_month, ss.modified, sd.parentfield, afno, afcode, afhead
	""",
        (docname),
        as_dict=1,
    )

    # frappe.log_error("Wait", salary_slips)
    # frappe.throw("Wait")

    if not salary_slips:
        return None

    # update Provident fund actuals
    basic_actuals = next(
        (item["actuals"] or 0 for item in salary_slips if item["afhead"] == "BASIC"), 0
    )
    pf_expected = round(basic_actuals * 0.12, 0)

    # update ESIC actuals
    esic_actuals_sum = sum(
        (item["actuals"] or 0) for item in salary_slips if item["afno"].startswith("E")
    )
    esic_base = round(esic_actuals_sum * 0.0075, 0)

    for item in salary_slips:
        if item["afcode"] == "PF":
            if item.get("actuals") is not None and item.get("actuals") > 0:
                item["actuals"] = pf_expected
            elif item.get("actuals") is None:
                item["actuals"] = 0
                item["afrate"] = 0
        if item["afcode"] == "ESIC":
            if item.get("actuals") is not None and item.get("actuals") > 0:
                item["actuals"] = esic_base
            elif item.get("actuals") is None:
                item["actuals"] = 0
                item["afrate"] = 0

    # Merge the Lending app loan repayment into the ERP 'Loan' component.
    _merge_lending_loan_into_erp_rows(salary_slips, docname)

    sql_queries = []
    for salary_slip in salary_slips:
        keys = []
        values = []
        for key, value in map.items():
            if value:
                keys.append(key)
                value_to_insert = salary_slip[value]
                if value_to_insert is None:
                    values.append("")
                elif value_to_insert == "rate_identifier":
                    get_indicator_query = f"SELECT AFRATEI FROM RIPLRR.EMP_CONFIG_MAST WHERE AFCODE = '{salary_slip['afcode']}' AND EMP_CATG = '{salary_slip['custom_emp_category']}' AND ENTITY_CODE = '{salary_slip['entity_code']}' AND TO_DATE IS NULL"
                    values.append(f"({get_indicator_query})")

                else:
                    if "from_date" in value:
                        values.append(
                            f"TO_DATE('{value_to_insert} 00:00:00', 'YYYY-MM-DD HH24:MI:SS')"
                        )
                    elif "modified" in value:
                        value_to_insert = str(value_to_insert).split(".")
                        values.append(
                            f"TO_DATE('{value_to_insert[0]}', 'YYYY-MM-DD HH24:MI:SS')"
                        )
                    elif "afrate" in value:
                        values.append(value_to_insert)
                    else:
                        values.append(f"{value_to_insert}")

        formatted_values = []
        for elem in values:
            if type(elem) == int or type(elem) == float:
                formatted_values.append(f"{float(elem)}")
            else:
                elem_str = str(elem)
                if "TO_DATE" in elem_str:
                    formatted_values.append(elem_str)
                else:
                    formatted_values.append("'" + elem_str + "'")

        sql = f"""
			INSERT INTO {table_name}
				({','.join([str(elem) for elem in keys])})
			VALUES
				({','.join(formatted_values)})
		"""

        sql_queries.append(sql)

    sql_dict = {
        "sql_queries": sql_queries,
        "emp_code": salary_slips[0].emp_code,
        "cal_year": salary_slips[0].custom_calendar_year,
        "month": salary_slips[0].custom_month,
    }

    return sql_dict


def get_salary_slip_update_query(map, table_name, docname, doc_salary_structure):
    salary_slips = frappe.db.sql(
        """
		SELECT
			employee AS emp_code,
			ss.start_date AS from_date,
			EXTRACT(YEAR FROM ss.start_date) AS custom_calendar_year,
			UPPER(TRIM(TO_CHAR(ss.start_date, 'MON'))) AS custom_month,
			ss.modified,
			sd.parentfield,
			CASE 
				WHEN sd.parentfield = 'earnings' THEN CONCAT('E', sd.idx)
				WHEN sd.parentfield = 'deductions' THEN CONCAT('D', sd.idx)
				ELSE sd.idx
			END AS afno,
			(SELECT custom_erp_code FROM `tabSalary Component` WHERE name = sd.salary_component LIMIT 1) AS afcode,
			LEFT(UPPER(sd.salary_component), 15) AS afhead,
			-- sd.custom_erp_rate AS afrate,
			CASE 
				WHEN sd.custom_erp_rate_indicator = 'D' AND sd.salary_component = 'Labour Welfare Fund' THEN ss_sd.amount
				WHEN sd.custom_erp_rate_indicator IN ('L', 'D', 'R') AND sd.salary_component != 'Labour Welfare Fund' THEN sd.amount
				WHEN sd.custom_erp_rate_indicator IN ('P', 'Q', 'C', 'F') THEN sd.custom_erp_rate
			END AS afrate,
			'rate_identifier' AS afratei,
			(SELECT custom_erp_code FROM `tabCompany` WHERE name = ss.company LIMIT 1) AS entity_code,
			(SELECT erp_code FROM `tabDivision` WHERE name = ss.custom_division LIMIT 1) AS custom_division,
			(SELECT erp_code FROM `tabEmployee Category` WHERE name = ss.custom_employee_category LIMIT 1) AS custom_emp_category,
			(SELECT erp_code FROM `tabPayroll Series` WHERE name = ss.custom_payroll_series LIMIT 1) AS custom_payroll_series,
			(SELECT username FROM `tabUser` WHERE name = ss.owner) AS user_code,
			IFNULL(SUM(ss_sd.amount), 0) AS afield,
			-- IFNULL(SUM(ss_sd.amount), 0) AS actuals,
			-- sd.amount AS actuals
			CASE 
				WHEN sd.custom_erp_rate_indicator = 'D' AND sd.salary_component = 'Labour Welfare Fund' THEN ss_sd.amount
				WHEN sd.custom_erp_rate_indicator IN ('L', 'D', 'R') AND sd.salary_component != 'Labour Welfare Fund' THEN sd.amount
				WHEN sd.custom_erp_rate_indicator IN ('P', 'Q', 'C', 'F') THEN ss_sd.amount
			END AS actuals
		FROM
			`tabSalary Slip` AS ss
		LEFT JOIN
			`tabSalary Detail` AS sd ON sd.parent = ss.salary_structure
		LEFT JOIN
			`tabSalary Detail` AS ss_sd ON ss_sd.parent = ss.name AND (SELECT custom_erp_code FROM `tabSalary Component` WHERE name = ss_sd.salary_component LIMIT 1) = (SELECT custom_erp_code FROM `tabSalary Component` WHERE name = sd.salary_component LIMIT 1)
		WHERE
			ss.name = %s
		GROUP BY
			employee, ss.start_date, custom_calendar_year, custom_month, ss.modified, sd.parentfield, afno, afcode, afhead
	""",
        (docname),
        as_dict=1,
    )

    # frappe.log_error("Wait Update", salary_slips)
    # frappe.throw("salary_slips")

    if not salary_slips:
        return None

    # update Provident fund actuals
    basic_actuals = next(
        (item["actuals"] or 0 for item in salary_slips if item["afhead"] == "BASIC"), 0
    )
    pf_expected = round(basic_actuals * 0.12, 0)

    # update ESIC actuals
    esic_actuals_sum = sum(
        (item["actuals"] or 0) for item in salary_slips if item["afno"].startswith("E")
    )
    esic_base = round(esic_actuals_sum * 0.0075, 0)

    for item in salary_slips:
        if item["afcode"] == "PF":
            if item.get("actuals") is not None and item.get("actuals") > 0:
                item["actuals"] = pf_expected
            elif item.get("actuals") is None:
                item["actuals"] = 0
                item["afrate"] = 0
        if item["afcode"] == "ESIC":
            if item.get("actuals") is not None and item.get("actuals") > 0:
                item["actuals"] = esic_base
            elif item.get("actuals") is None:
                item["actuals"] = 0
                item["afrate"] = 0

    # Merge the Lending app loan repayment into the ERP 'Loan' component.
    _merge_lending_loan_into_erp_rows(salary_slips, docname)

    sql_queries = []
    for salary_slip in salary_slips:
        sets = []
        conditions = []
        for key, value in map.items():
            if value:
                if value == "emp_code":
                    conditions.append(
                        f"{key} = '{salary_slip[value]}' AND AFNO = '{salary_slip['afno']}' AND CAL_YEAR = '{salary_slip['custom_calendar_year']}' AND MONTH = '{salary_slip['custom_month']}' "
                    )
                else:
                    value_to_insert = salary_slip[value]
                    if value_to_insert is None:
                        sets.append(f"{key} = ''")
                    elif value_to_insert == "rate_identifier":
                        get_indicator_query = f"SELECT AFRATEI FROM RIPLRR.EMP_CONFIG_MAST WHERE AFCODE = '{salary_slip['afcode']}' AND EMP_CATG = '{salary_slip['custom_emp_category']}' AND ENTITY_CODE = '{salary_slip['entity_code']}' AND TO_DATE IS NULL"
                        sets.append(f"{key} = ({get_indicator_query})")

                    else:
                        if "from_date" in value:
                            sets.append(
                                f"{key} = TO_DATE('{value_to_insert} 00:00:00', 'YYYY-MM-DD HH24:MI:SS')"
                            )
                        elif "modified" in value:
                            value_to_insert = str(value_to_insert).split(".")
                            sets.append(
                                f"{key} = TO_DATE('{value_to_insert[0]}', 'YYYY-MM-DD HH24:MI:SS')"
                            )
                        elif "afrate" in value:
                            sets.append(f"{key} = {value_to_insert}")
                        else:
                            sets.append(f"{key} = '{value_to_insert}'")

        sql = f"""
			UPDATE {table_name}
			SET {','.join([str(elem) for elem in sets])}
			WHERE {' AND '.join([str(elem) for elem in conditions])}
		"""

        sql_queries.append(sql)

    sql_dict = {
        "sql_queries": sql_queries,
        "emp_code": salary_slips[0].emp_code,
        "cal_year": salary_slips[0].custom_calendar_year,
        "month": salary_slips[0].custom_month,
    }

    return sql_dict


def get_attendance_balance_insert_query(map, table_name, docname):
    salary_slip = frappe.db.sql(
        """
            SELECT
                EXTRACT(YEAR FROM ss.start_date) AS custom_calendar_year,
                EXTRACT(MONTH FROM ss.end_date) AS custom_month,
                UPPER(TRIM(TO_CHAR(ss.start_date, 'MON'))) AS custom_month_char,
                ss.employee AS emp_code,
                (SELECT custom_erp_code FROM `tabCompany` WHERE name = ss.company  LIMIT 1) as entity_code,
                ss.company,
                e.branch,
                e.custom_division AS division,
                e.department,
                ss.modified,
                (SELECT username FROM `tabUser` WHERE name = ss.owner) as user_code,
                e.leave_approver as leave_approver
            FROM
                `tabSalary Slip` as ss
		LEFT JOIN
			`tabEmployee` as e ON e.name = ss.employee
		WHERE
			ss.name = %s
		""",
        (docname),
        as_dict=1,
    )

    # Fetching the basic data form Salary Slip

    cal_year = salary_slip[0].get("custom_calendar_year")
    month = salary_slip[0].get("custom_month")
    month_char = salary_slip[0].get("custom_month_char")
    employee = salary_slip[0].get("emp_code")
    company = salary_slip[0].get("company")
    branch = salary_slip[0].get("branch")
    division = salary_slip[0].get("division")
    department = salary_slip[0].get("department")
    lastupdate = salary_slip[0].get("modified")
    usercode = salary_slip[0].get("user_code")
    leave_approver = salary_slip[0].get("leave_approver")

    # fetching the data from standard report(Monthly Attendance Sheet) don't need to change
    month_characters = {
        1: "Jan",
        2: "Feb",
        3: "Mar",
        4: "Apr",
        5: "May",
        6: "Jun",
        7: "Jul",
        8: "Aug",
        9: "Sep",
        10: "Oct",
        11: "Nov",
        12: "Dec",
    }

    # fetching the data from standard report(Monthly Attendance Sheet) don't need to change
    report_filters = {
        "month": month_characters[month],
        "year": cal_year,
        "employee": employee,
        "company": company,
    }
    if branch:
        report_filters["branch"] = branch
    if division:
        report_filters["division"] = division
    if department:
        report_filters["department"] = department

    result = frappe.call(
        "frappe.desk.query_report.run",
        report_name="[New] Monthly Attendance Report",
        filters=report_filters,
        ignore_prepared_report=True,
    )

    report_rows = (result or {}).get("result") or []
    temp_result = {}
    if report_rows and isinstance(report_rows[0], dict):
        temp_result = next(
            (row for row in report_rows if row.get("employee") == employee),
            report_rows[0],
        )

    # needs to map new leave type here
    temp_result = {
        "PRESENT": temp_result.get("total_present", 0.0),
        "ABSENT_LOP": temp_result.get("total_absent", 0.0)
        + temp_result.get("leave_without_pay", 0.0),
        "HOLIDAY": temp_result.get("total_holiday_leave", 0.0),
        "OPTIONAL_LEAVE": temp_result.get("optional_leave", 0.0),
        "SICK_LEAVE": temp_result.get("sick_leave", 0.0),
        "ESIC_LEAVE": temp_result.get("esic_leave", 0.0),
        "COMPENSATORY_OFF": temp_result.get("total_compensatory_off", 0.0),
        "CASUAL_LEAVE": temp_result.get("total_casual_leave", 0.0),
        "EARNED_LEAVE": temp_result.get("total_earned_leave", 0.0),
        "NIGHT": temp_result.get("night", 0.0),
        # "TOUR": temp_result.get("total_tour", 0.0),
        "APPROVED_LEAVE": temp_result.get("approved_leave", 0.0),
        "WEEKLY_OFF": temp_result.get("total_wo", 0.0),
        "OUTDOOR_DUTY_LEAVE": temp_result.get("total_od", 0.0),
        "LATE_PENALTY": temp_result.get("late_penalty", 0.0),
        "FULL_AND_FINAL_EARNING": temp_result.get("full_and_final_earning", 0.0),
        "FULL_AND_FINAL_DEDUCTION": temp_result.get("full_and_final_deduction", 0.0),
    }

    final_result = []
    # Needs to map the ERP Attend Char here which are not present in leave type
    leave_type_map = {
        "PRESENT": "P",
        "ABSENT_LOP": "A",
        "HOLIDAY": "H",
        "NIGHT": "B",
        "TOUR": "T",
        "APPROVED_LEAVE": "M",
        "WEEKLY_OFF": "R",
        "OUTDOOR_DUTY_LEAVE": "O",
        "LATE_PENALTY": "N",
        "FULL_AND_FINAL_EARNING": "F",
        "FULL_AND_FINAL_DEDUCTION": "D",
        "EARNED_LEAVE": "E",
        "CASUAL_LEAVE": "L",
        "COMPENSATORY_OFF": "C",
        "SICK_LEAVE": "S",
        "ESIC_LEAVE": "I",
        "OPTIONAL_LEAVE": "X",
    }

    for rec in temp_result:
        leave_type = rec.replace(
            "_", " "
        ).title()  # Replace the leave name to title case
        if frappe.db.exists(
            "Leave Type", leave_type
        ):  # checing leave type present or not
            attand_char = frappe.db.get_value(
                "Leave Type", leave_type, "custom_erp_attend_char"
            )  # present then append
        else:
            attand_char = leave_type_map.get(
                rec, ""
            )  # append from leave_type_map which are define in above lines

        if attand_char:
            attend_bal_rec = {
                "cal_year": cal_year,
                "month": month_char,
                "emp_code": employee,
                "attend_char": attand_char,
                "days": float(temp_result[rec]),
                "user_code": usercode,
                "lastupdate": lastupdate,
                "approvedby": leave_approver,
                "approveddate": lastupdate,
            }
            final_result.append(attend_bal_rec)

    attend_chars = final_result

    if not attend_chars:
        return None

    sql_queries = []
    for attend_char in attend_chars:
        keys = []
        values = []
        for key, value in map.items():
            if value:
                keys.append(key)
                value_to_insert = attend_char[value]
                if value_to_insert is None:
                    values.append("")
                else:
                    if "lastupdate" in value:
                        # values.append(f"TO_DATE('{value_to_insert} 00:00:00', 'YYYY-MM-DD HH24:MI:SS')")
                        value_to_insert = str(value_to_insert).split(".")
                        values.append(
                            f"TO_DATE('{value_to_insert[0]}', 'YYYY-MM-DD HH24:MI:SS')"
                        )
                    elif "approveddate" in value:
                        value_to_insert = str(value_to_insert).split(".")
                        values.append(
                            f"TO_DATE('{value_to_insert[0].split(' ')[0]} 00:00:00', 'YYYY-MM-DD HH24:MI:SS')"
                        )
                    else:
                        values.append(f"{value_to_insert}")

        formatted_values = []
        for elem in values:
            if isinstance(elem, (int | float)):
                formatted_values.append(f"{float(elem)}")
            else:
                elem_str = str(elem)
                if "TO_DATE" in elem_str:
                    formatted_values.append(elem_str)
                else:
                    formatted_values.append("'" + elem_str + "'")

        sql = f"""
			INSERT INTO {table_name}
				({",".join([str(elem) for elem in keys])})
			VALUES
				({",".join(formatted_values)})
		"""

        sql_queries.append(sql)

    sql_dict = {
        "sql_queries": sql_queries,
        "emp_code": employee,
        "cal_year": cal_year,
        "month": month_char,
    }

    return sql_dict


def get_attendance_balance_update_query(map, table_name, docname):
    salary_slip = frappe.db.sql(
        """
            SELECT
                EXTRACT(YEAR FROM ss.start_date) AS custom_calendar_year,
                EXTRACT(MONTH FROM ss.end_date) AS custom_month,
                UPPER(TRIM(TO_CHAR(ss.start_date, 'MON'))) AS custom_month_char,
                ss.employee AS emp_code,
                (SELECT custom_erp_code FROM `tabCompany` WHERE name = ss.company  LIMIT 1) as entity_code,
                ss.company,
                e.branch,
                e.custom_division AS division,
                e.department,
                ss.modified,
                (SELECT username FROM `tabUser` WHERE name = ss.owner) as user_code,
                e.leave_approver as leave_approver
            FROM
                `tabSalary Slip` as ss
		LEFT JOIN
			`tabEmployee` as e ON e.name = ss.employee
		WHERE
			ss.name = %s
		""",
        (docname),
        as_dict=1,
    )

    # Fetching the basic data form Salary Slip

    cal_year = salary_slip[0].get("custom_calendar_year")
    month = salary_slip[0].get("custom_month")
    month_char = salary_slip[0].get("custom_month_char")
    employee = salary_slip[0].get("emp_code")
    company = salary_slip[0].get("company")
    branch = salary_slip[0].get("branch")
    division = salary_slip[0].get("division")
    department = salary_slip[0].get("department")
    lastupdate = salary_slip[0].get("modified")
    usercode = salary_slip[0].get("user_code")
    leave_approver = salary_slip[0].get("leave_approver")

    month_characters = {
        1: "Jan",
        2: "Feb",
        3: "Mar",
        4: "Apr",
        5: "May",
        6: "Jun",
        7: "Jul",
        8: "Aug",
        9: "Sep",
        10: "Oct",
        11: "Nov",
        12: "Dec",
    }

    # fetching the data from standard report(Monthly Attendance Sheet) don't need to change
    report_filters = {
        "month": month_characters[month],
        "year": cal_year,
        "employee": employee,
        "company": company,
    }
    if branch:
        report_filters["branch"] = branch
    if division:
        report_filters["division"] = division
    if department:
        report_filters["department"] = department

    result = frappe.call(
        "frappe.desk.query_report.run",
        report_name="[New] Monthly Attendance Report",
        filters=report_filters,
        ignore_prepared_report=True,
    )
    report_rows = (result or {}).get("result") or []
    temp_result = {}
    if report_rows and isinstance(report_rows[0], dict):
        temp_result = next(
            (row for row in report_rows if row.get("employee") == employee),
            report_rows[0],
        )

    # needs to map new leave type here
    temp_result = {
        "PRESENT": temp_result.get("total_present", 0.0),
        "ABSENT_LOP": temp_result.get("total_absent", 0.0),
        "HOLIDAY": temp_result.get("total_holiday_leave", 0.0),
        "OPTIONAL_LEAVE": temp_result.get("optional_leave", 0.0),
        "SICK_LEAVE": temp_result.get("sick_leave", 0.0),
        "ESIC_LEAVE": temp_result.get("esic_leave", 0.0),
        "COMPENSATORY_OFF": temp_result.get("total_compensatory_off", 0.0),
        "CASUAL_LEAVE": temp_result.get("total_casual_leave", 0.0),
        "EARNED_LEAVE": temp_result.get("total_earned_leave", 0.0),
        "NIGHT": temp_result.get("night", 0.0),
        # "TOUR": temp_result.get("total_tour", 0.0),
        "APPROVED_LEAVE": temp_result.get("approved_leave", 0.0),
        "WEEKLY_OFF": temp_result.get("total_wo", 0.0),
        "OUTDOOR_DUTY_LEAVE": temp_result.get("total_od", 0.0),
        "LATE_PENALTY": temp_result.get("late_penalty", 0.0),
        "FULL_AND_FINAL_EARNING": temp_result.get("full_and_final_earning", 0.0),
        "FULL_AND_FINAL_DEDUCTION": temp_result.get("full_and_final_deduction", 0.0),
    }

    final_result = []
    # Needs to map the ERP Attend Char here which are not present in leave type
    leave_type_map = {
        "PRESENT": "P",
        "ABSENT_LOP": "A",
        "HOLIDAY": "H",
        "NIGHT": "B",
        "TOUR": "T",
        "APPROVED_LEAVE": "M",
        "WEEKLY_OFF": "R",
        "OUTDOOR_DUTY_LEAVE": "O",
        "LATE_PENALTY": "N",
        "FULL_AND_FINAL_EARNING": "F",
        "FULL_AND_FINAL_DEDUCTION": "D",
        "EARNED_LEAVE": "E",
        "CASUAL_LEAVE": "L",
        "COMPENSATORY_OFF": "C",
        "SICK_LEAVE": "S",
        "ESIC_LEAVE": "I",
        "OPTIONAL_LEAVE": "X",
    }

    for rec in temp_result:
        leave_type = rec.replace(
            "_", " "
        ).title()  # Replace the leave name to title case
        if frappe.db.exists(
            "Leave Type", leave_type
        ):  # checing leave type present or not
            attand_char = frappe.db.get_value(
                "Leave Type", leave_type, "custom_erp_attend_char"
            )  # present then append
        else:
            attand_char = leave_type_map.get(
                rec, ""
            )  # append from leave_type_map which are define in above lines

        if attand_char:
            attend_bal_rec = {
                "cal_year": cal_year,
                "month": month_char,
                "emp_code": employee,
                "attend_char": attand_char,
                "days": float(temp_result[rec]),
                "user_code": usercode,
                "lastupdate": lastupdate,
                "approvedby": leave_approver,
                "approveddate": lastupdate,
            }
            final_result.append(attend_bal_rec)

    attend_chars = final_result

    if not attend_chars:
        return None

    sql_queries = []
    for attend_char in attend_chars:
        sets = []
        conditions = []
        for key, value in map.items():
            if value:
                if value == "emp_code":
                    conditions.append(
                        f"{key} = '{attend_char[value]}' AND CAL_YEAR = '{attend_char['cal_year']}' AND MONTH = '{attend_char['month']}' AND ATTEND_CHAR = '{attend_char['attend_char']}' "
                    )
                else:
                    value_to_insert = attend_char[value]
                    if value_to_insert is None:
                        sets.append(f"{key} = ''")
                    else:
                        if "lastupdate" in value:
                            value_to_insert = str(value_to_insert).split(".")
                            sets.append(
                                f"{key} = TO_DATE('{value_to_insert[0]}', 'YYYY-MM-DD HH24:MI:SS')"
                            )
                        elif "approveddate" in value:
                            value_to_insert = str(value_to_insert).split(".")
                            sets.append(
                                f"{key} = TO_DATE('{value_to_insert[0].split(' ')[0]} 00:00:00', 'YYYY-MM-DD HH24:MI:SS')"
                            )
                        else:
                            sets.append(f"{key} = '{value_to_insert}'")

        sql = f"""
			UPDATE {table_name}
			SET {",".join([str(elem) for elem in sets])}
			WHERE {" AND ".join([str(elem) for elem in conditions])}
		"""

        sql_queries.append(sql)

    sql_dict = {
        "sql_queries": sql_queries,
        "emp_code": employee,
        "cal_year": cal_year,
        "month": month_char,
    }

    return sql_dict


def get_bonus_transaction_insert_query(map, table_name, docname, series):
    bonus_trans = frappe.db.sql(
        """
		SELECT
			ss.employee AS emp_code,
			'BASIC' AS afcode_str,
			(SELECT amount FROM `tabSalary Detail` WHERE parent = ss.name AND abbr = 'B') AS basic_amt,
			(SELECT username FROM `tabUser` WHERE name = ss.owner) as user_code,
			ss.modified AS lastupdate,
			ss.posting_date AS bonus_cal_date,
			ss.start_date AS from_date,
			ss.end_date AS to_date,
			ss.custom_bonus_rate AS bonus_cal_rate,
			CASE
				WHEN ss.custom_bonus_amount - FLOOR(ss.custom_bonus_amount) < 0.5 THEN FLOOR(ss.custom_bonus_amount)
				ELSE CEIL(ss.custom_bonus_amount)
			END AS bonus_amt,
			%s AS vrno,
			ss.posting_date AS vrdate,
			ss.payment_days AS paydays,
			(SELECT custom_erp_code FROM `tabCompany` WHERE name = ss.company  LIMIT 1) as entity_code,
			(SELECT erp_code FROM `tabDivision` WHERE name = ss.custom_division  LIMIT 1) as div_code,
			(SELECT erp_code FROM `tabEmployee Category` WHERE name = ss.custom_employee_category LIMIT 1) as custom_emp_category,
			(SELECT erp_code FROM `tabPayroll Series` WHERE name = ss.custom_payroll_series LIMIT 1) as custom_payroll_series
		FROM
			`tabSalary Slip` as ss
		WHERE
			ss.name = %s
		""",
        (series, docname),
        as_dict=1,
    )

    if not bonus_trans:
        return None

    bonus_tran = bonus_trans[0]

    keys = []
    values = []
    for key, value in map.items():
        if value:
            keys.append(key)
            value_to_insert = bonus_tran[value]
            if value_to_insert is None:
                values.append("")
            else:
                if "from_date" in value or "to_date" in value or "vrdate" in value:
                    values.append(
                        f"TO_DATE('{value_to_insert} 00:00:00', 'YYYY-MM-DD HH24:MI:SS')"
                    )
                elif "bonus_cal_date" in value or "lastupdate" in value:
                    value_to_insert = str(value_to_insert).split(".")
                    values.append(
                        f"TO_DATE('{value_to_insert[0]}', 'YYYY-MM-DD HH24:MI:SS')"
                    )
                elif "afcode_str" in value:
                    values.append(f",{value_to_insert},")
                else:
                    values.append(f"{value_to_insert}")

    formatted_values = []
    for elem in values:
        if isinstance(elem, (int | float)):
            formatted_values.append(f"{float(elem)}")
        else:
            elem_str = str(elem)
            if "TO_DATE" in elem_str:
                formatted_values.append(elem_str)
            else:
                formatted_values.append("'" + elem_str + "'")

    sql = f"""
		INSERT INTO {table_name}
			({",".join([str(elem) for elem in keys])})
		VALUES
			({",".join(formatted_values)})
	"""

    sql_dict = {"sql_query": sql, "emp_code": bonus_tran.emp_code}

    return sql_dict


def get_bonus_transaction_update_query(map, table_name, docname, series):
    bonus_trans = frappe.db.sql(
        """
		SELECT
			ss.employee AS emp_code,
			'BASIC' AS afcode_str,
			(SELECT amount FROM `tabSalary Detail` WHERE parent = ss.name AND abbr = 'B') AS basic_amt,
			(SELECT username FROM `tabUser` WHERE name = ss.owner) as user_code,
			ss.modified AS lastupdate,
			ss.posting_date AS bonus_cal_date,
			ss.start_date AS from_date,
			ss.end_date AS to_date,
			ss.custom_bonus_rate AS bonus_cal_rate,
			CASE
				WHEN ss.custom_bonus_amount - FLOOR(ss.custom_bonus_amount) < 0.5 THEN FLOOR(ss.custom_bonus_amount)
				ELSE CEIL(ss.custom_bonus_amount)
			END AS bonus_amt,
			%s AS vrno,
			ss.posting_date AS vrdate,
			ss.payment_days AS paydays,
			(SELECT custom_erp_code FROM `tabCompany` WHERE name = ss.company  LIMIT 1) as entity_code,
			(SELECT erp_code FROM `tabDivision` WHERE name = ss.custom_division  LIMIT 1) as div_code,
			(SELECT erp_code FROM `tabEmployee Category` WHERE name = ss.custom_employee_category LIMIT 1) as custom_emp_category,
			(SELECT erp_code FROM `tabPayroll Series` WHERE name = ss.custom_payroll_series LIMIT 1) as custom_payroll_series
		FROM
			`tabSalary Slip` as ss
		WHERE
			ss.name = %s
		""",
        (series, docname),
        as_dict=1,
    )

    if not bonus_trans:
        return None

    bonus_tran = bonus_trans[0]

    sets = []
    conditions = []
    for key, value in map.items():
        if value:
            if value == "emp_code":
                # conditions.append(f"{key} = '{bonus_tran[value]}' AND ENTITY_CODE = '{bonus_tran['entity_code']}' AND VRNO = '{bonus_tran['vrno']}'")
                conditions.append(
                    f"{key} = '{bonus_tran[value]}' AND ENTITY_CODE = '{bonus_tran['entity_code']}' AND FROM_DATE = TO_DATE('{bonus_tran['from_date']} 00:00:00', 'YYYY-MM-DD HH24:MI:SS') AND TO_DATE = TO_DATE('{bonus_tran['to_date']} 00:00:00', 'YYYY-MM-DD HH24:MI:SS')"
                )
            else:
                value_to_insert = bonus_tran[value]
                if value_to_insert is None:
                    sets.append(f"{key} = ''")
                else:
                    if "from_date" in value or "to_date" in value or "vrdate" in value:
                        sets.append(
                            f"{key} = TO_DATE('{value_to_insert} 00:00:00', 'YYYY-MM-DD HH24:MI:SS')"
                        )
                    elif "bonus_cal_date" in value or "lastupdate" in value:
                        value_to_insert = str(value_to_insert).split(".")
                        sets.append(
                            f"{key} = TO_DATE('{value_to_insert[0]}', 'YYYY-MM-DD HH24:MI:SS')"
                        )
                    elif "afcode_str" in value:
                        sets.append(f"{key} = ',{value_to_insert},'")
                    else:
                        sets.append(f"{key} = '{value_to_insert}'")

    sql = f"""
		UPDATE {table_name}
		SET {",".join([str(elem) for elem in sets])}
		WHERE {" AND ".join([str(elem) for elem in conditions])}
	"""

    sql_dict = {"sql_query": sql, "emp_code": bonus_tran.emp_code}

    return sql_dict


# Fetch ERP Config Master Details From this
@frappe.whitelist()
def config_master(emp_catg, company):
    company_full_name = company
    category = frappe.db.get_value("Employee Category", emp_catg, "erp_code")
    company = frappe.db.get_value("Company", company, "custom_erp_code")

    con = oracle_connection(company_full_name)
    if not con:
        frappe.log_error(title="Oracle Connection information is not set")
    else:
        try:
            cur = con.cursor()
            if category is None or company is None:
                frappe.throw("ERP Code Not Found For Category or Company")

            else:
                sql_query = f"""
					SELECT
						AFNO,
						AFCODE,
						AFHEAD,
						AFRATEI,
						AFRATE
					FROM
						RIPLRR.EMP_CONFIG_MAST
					WHERE
						EMP_CATG = '{category}'
						AND ENTITY_CODE = '{company}'
						AND TO_DATE IS NULL
					ORDER BY
						SUBSTR(AFNO, 1, 1),
						TO_NUMBER(SUBSTR(AFNO, 2))
					"""

                cur.execute(sql_query)
                result = cur.fetchall()

                result_list = []
                for row in result:
                    result_dict = {}
                    for idx, col in enumerate(cur.description):
                        if isinstance(row[idx], datetime):
                            result_dict[col[0]] = row[idx].isoformat()
                        else:
                            result_dict[col[0]] = row[idx]
                    result_list.append(result_dict)

                for rec in result_list:
                    if rec.get("AFCODE"):
                        salary_component = frappe.db.get_value(
                            "Salary Component",
                            {"custom_erp_code": rec.get("AFCODE")},
                            "name",
                        )
                        salary_component_abbr = frappe.db.get_value(
                            "Salary Component",
                            {"custom_erp_code": rec.get("AFCODE")},
                            "salary_component_abbr",
                        )
                        rec["salary_component"] = salary_component
                        rec["abbr"] = salary_component_abbr

                msg = result_list

            # con.commit() #-----------------Database commit value

        except cx_Oracle.DatabaseError as er:
            frappe.log_error(title="Oracle Query Error", message=er)
            frappe.throw(f"Oracle Query Error: {er!s}")
            con.rollback()

        except Exception as er:
            frappe.log_error(title="Oracle Exception", message=er)
            frappe.throw(f"Oracle Exception: {er!s}")
            con.rollback()

        finally:
            if cur:
                cur.close()

            if con:
                con.close()

    return msg


# Fetch ERP Config Master Details From this
@frappe.whitelist()
def erp_config_master(emp_catg, company):
    company_full_name = company
    category = frappe.db.get_value("Employee Category", emp_catg, "erp_code")
    company = frappe.db.get_value("Company", company, "custom_erp_code")

    con = oracle_connection(company_full_name)
    if not con:
        frappe.log_error(title="Oracle Connection information is not set")
    else:
        try:
            cur = con.cursor()
            if category is None or company is None:
                frappe.throw("ERP Code Not Found For Category or Company")
            else:
                sql_query = f"""
					SELECT
						AFNO,
						AFCODE,
						AFHEAD,
						AFRATEI,
						AFRATE
					FROM
						RIPLRR.EMP_CONFIG_MAST
					WHERE
						EMP_CATG = '{category}'
						AND ENTITY_CODE = '{company}'
						AND TO_DATE IS NULL
					ORDER BY
						SUBSTR(AFNO, 1, 1),
						TO_NUMBER(SUBSTR(AFNO, 2))
					"""

                cur.execute(sql_query)
                result = cur.fetchall()

                result_list = []
                for row in result:
                    result_dict = {}
                    for idx, col in enumerate(cur.description):
                        if isinstance(row[idx], datetime):
                            result_dict[col[0]] = row[idx].isoformat()
                        else:
                            result_dict[col[0]] = row[idx]
                    result_list.append(result_dict)

                for rec in result_list:
                    if rec.get("AFCODE"):
                        salary_component = frappe.db.get_value(
                            "Salary Component",
                            {"custom_erp_code": rec.get("AFCODE")},
                            "name",
                        )
                        salary_component_abbr = frappe.db.get_value(
                            "Salary Component",
                            {"custom_erp_code": rec.get("AFCODE")},
                            "salary_component_abbr",
                        )
                        rec["salary_component"] = salary_component
                        rec["abbr"] = salary_component_abbr

                json_result = json.dumps(result_list)

                msg = json_result

            # con.commit() #-----------------Database commit value

        except cx_Oracle.DatabaseError as er:
            frappe.log_error(title="Oracle Query Error", message=er)
            frappe.throw(f"Oracle Query Error: {er!s}")
            con.rollback()

        except Exception as er:
            frappe.log_error(title="Oracle Exception", message=er)
            frappe.throw(f"Oracle Exception: {er!s}")
            con.rollback()

        finally:
            if cur:
                cur.close()
            if con:
                con.close()

        return msg if msg else "[]"


# Fetch ERP Config Master Details From this
@frappe.whitelist()
def employee_rate_master(emp_code, company):
    con = oracle_connection(company)
    if not con:
        frappe.log_error(title="Oracle Connection information is not set")
    else:
        try:
            cur = con.cursor()
            sql_query = f""" SELECT AFRATE, AFNO, AFCODE FROM RIPLRR.EMP_RATE_MAST WHERE EMP_CODE = '{emp_code}' AND TO_DATE IS NULL """
            cur.execute(sql_query)
            result = cur.fetchall()
            result_list = []
            for row in result:
                result_dict = {}
                for idx, col in enumerate(cur.description):
                    if isinstance(row[idx], datetime):
                        result_dict[col[0]] = row[idx].isoformat()
                    else:
                        result_dict[col[0]] = row[idx]
                result_list.append(result_dict)

            msg = result_list

        except cx_Oracle.DatabaseError as er:
            frappe.log_error(title="Oracle Query Error", message=er)
            frappe.throw(f"Oracle Query Error: {er!s}")
            con.rollback()

        except Exception as er:
            frappe.log_error(title="Oracle Exception", message=er)
            frappe.throw(f"Oracle Exception: {er!s}")
            con.rollback()

        finally:
            if cur:
                cur.close()

            if con:
                con.close()

    return msg


def get_next_series_no(doctype, company, date, con, cur):
    erp_series = frappe.get_doc(
        "ERP Series Master", {"document_type": doctype, "company": company}
    )
    if not erp_series:
        frappe.throw("ERP Series Master Not Defined")

    fy = frappe.db.sql(
        f"SELECT name FROM `tabFiscal Year` WHERE '{date}' BETWEEN year_start_date AND year_end_date",
        as_dict=1,
    )
    if not fy:
        frappe.throw("Fiscal Year Not defined for the Bonus Transaction Date")

    fiscal_year = fy[0].name[2:4]
    base_series = f"{erp_series.series_prefix}"
    entity_code = frappe.db.get_value("Company", company, "custom_erp_code")

    if erp_series.formatter == "YYY":
        actual_base_series = f"{base_series}{fiscal_year}Y-"
        formatted_vrno = True
    elif erp_series.formatter == "YYM":
        dt = datetime.strptime(str(date), "%Y-%m-%d")
        month_abbr = (
            ["O", "N", "D"][dt.month - 10]
            if dt.month in (10, 11, 12)
            else str(dt.month)
        )
        actual_base_series = f"{base_series}{fiscal_year}{month_abbr}-"
        formatted_vrno = False
    else:
        frappe.throw("Formatter Not Found for ERP Series Master")

    vrprefix = f"{erp_series.tcode}{actual_base_series}"

    try:
        cur.execute(
            "SELECT LASTVRNO FROM RIPLRR.VRSEQ_MAST WHERE ENTITY_CODE=:1 AND VRPREFIX=:2 FOR UPDATE",
            (entity_code, vrprefix),
        )
        row = cur.fetchone()

        if row:
            count = int(row[0] or 0)
            new_count = count + 1
            cur.execute(
                "UPDATE RIPLRR.VRSEQ_MAST SET LASTVRNO=:1 WHERE ENTITY_CODE=:2 AND VRPREFIX=:3",
                (new_count, entity_code, vrprefix),
            )
        else:
            new_count = 1
            cur.execute(
                "INSERT INTO RIPLRR.VRSEQ_MAST (LASTVRNO, ENTITY_CODE, VRPREFIX) VALUES (:1, :2, :3)",
                (new_count, entity_code, vrprefix),
            )

        con.commit()  # release lock immediately
    except Exception:
        con.rollback()
        raise

    if formatted_vrno:
        return f"{actual_base_series}{str(new_count).zfill(5)}"
    return f"{actual_base_series}{new_count}"


def generate_insert_statements(salary_structure, emp_code, from_date):
    insert_statements = []
    from_date = frappe.utils.getdate(from_date)
    last_update = frappe.utils.getdate().strftime("%Y-%m-%d %H:%M:%S")
    formatted_date = frappe.utils.get_first_day(from_date).strftime("%Y-%m-%d %H:%M:%S")

    for entry in salary_structure:
        # Ensure numeric values are not passed as column names
        afrate = entry["afrate"] if entry["afrate"] is not None else 0
        afield = entry["afield"] if entry["afield"] is not None else 0

        sql = f"""
            INSERT INTO RIPLRR.EMP_RATE_MAST
            (EMP_CODE, FROM_DATE, AFNO, AFRATE, USER_CODE, LASTUPDATE, EMP_CONFIG_CATG, AFCODE, AFIELD, PAYROLL_SERIES)
            VALUES (
                '{emp_code}',
                TO_DATE('{formatted_date}', 'YYYY-MM-DD HH24:MI:SS'),
                '{entry["afno"]}',
                {float(afrate)},
                '{entry["user_code"]}',
                TO_DATE('{last_update}', 'YYYY-MM-DD HH24:MI:SS'),
                '{entry["custom_emp_category"]}',
                '{entry["afcode"]}',
                {float(afield)},
                '{entry["payroll_series"]}'
            )
        """
        insert_statements.append(sql.strip())

    return insert_statements


def insert_salary_structure(doc, method):
    con = oracle_connection(doc.company)
    if con is None:
        return
    try:
        cur = con.cursor()
        check_for_existing_record_sql = f"SELECT * FROM RIPLRR.EMP_RATE_MAST WHERE EMP_CODE = '{doc.employee}' AND FROM_DATE IS NOT NULL AND TO_DATE IS NULL"

        cur.execute(check_for_existing_record_sql)
        result_for_existing = cur.fetchall()
        if result_for_existing:
            update_salary_structure = f"""
				UPDATE RIPLRR.EMP_RATE_MAST
				SET TO_DATE = TO_DATE('{frappe.utils.get_last_day(frappe.utils.add_to_date(doc.from_date, months=-1)).strftime("%Y-%m-%d")}', 'YYYY-MM-DD'),
				LASTUPDATE = TO_DATE('{frappe.utils.now_datetime().strftime("%Y-%m-%d")} 00:00:00', 'YYYY-MM-DD HH24:MI:SS'),
				USER_CODE = '{doc.owner}'
				WHERE EMP_CODE = '{doc.employee}'
				AND FROM_DATE IS NOT NULL
				AND TO_DATE IS NULL
			"""

            cur.execute(update_salary_structure)

        salary_structure = get_salary_structure(
            doc.employee, doc.from_date, doc.salary_structure
        )

        sql_statements = generate_insert_statements(
            salary_structure, doc.employee, doc.from_date
        )

        # Execute each SQL statement separately
        for sql in sql_statements:
            cur.execute(sql)

        con.commit()

    except Exception as e:
        frappe.log_error(title="Oracle Query Error", message=str(e))
        con.rollback()
        frappe.throw(f"Oracle Query Error: {e!s}")


def get_salary_structure(employee, from_date, salary_structure):
    salary_structure_sql = frappe.db.sql(
        f"""
        SELECT
            (SELECT custom_erp_code FROM `tabSalary Component` WHERE name = sd.salary_component LIMIT 1) AS afcode,
            (SELECT erp_code FROM `tabEmployee Category` WHERE name = 'Staff' LIMIT 1) AS custom_emp_category,
            CASE
                WHEN sd.parentfield = 'earnings' THEN CONCAT('E', sd.idx)
                WHEN sd.parentfield = 'deductions' THEN CONCAT('D', sd.idx)
                ELSE sd.idx
            END AS afno,
            CASE
				WHEN sd.parentfield = 'deductions' AND sd.salary_component != 'Labour Welfare Fund' THEN sd.custom_erp_rate
				WHEN sd.parentfield = 'deductions' AND sd.salary_component = 'Labour Welfare Fund' AND ss.total_earning > 15000 THEN 10
				WHEN sd.parentfield = 'deductions' AND sd.salary_component = 'Labour Welfare Fund' AND ss.total_earning < 15000 THEN 5
				WHEN sd.parentfield = 'earnings' THEN sd.amount
            END afrate,
            sd.amount afield,
            (SELECT username FROM `tabUser` WHERE name = ss.owner) AS user_code,
            ss.modified
        FROM
            `tabSalary Structure` ss
        LEFT JOIN
            `tabSalary Detail` sd on sd.parent = ss.name
        WHERE
            ss.name = '{salary_structure}'
        GROUP BY
            sd.salary_component
    """,
        (),
        as_dict=True,
    )

    for d in salary_structure_sql:
        d["emp_code"] = employee
        emp_category = frappe.db.get_value("Employee", employee, "custom_emp_category")
        emp_category = frappe.db.get_value(
            "Employee Category", emp_category, "erp_code"
        )
        d["emp_category"] = emp_category
        d["custom_emp_category"] = emp_category
        payroll_series = frappe.db.get_value(
            "Employee", employee, "custom_payroll_series"
        )
        payroll_series = frappe.db.get_value(
            "Payroll Series", payroll_series, "erp_code"
        )
        d["payroll_series"] = payroll_series

    return salary_structure_sql
