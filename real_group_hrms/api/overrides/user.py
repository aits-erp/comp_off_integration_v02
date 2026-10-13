import cx_Oracle
import frappe
from frappe.core.doctype.user.user import _get_user_for_update_password
from frappe.core.doctype.user.user import update_password as _update_password

from real_group_hrms.real_group.integration import oracle_connection


def enqueue_oracle_password_sync(user: str, new_password: str):
    employee = frappe.db.get_value("Employee", user, ["name", "company"], as_dict=True)
    if not employee:
        frappe.log_error(
            title="Oracle Password Sync Skipped",
            message=f"Employee not found for user {user}",
        )
        return

    if not employee.company:
        frappe.log_error(
            title="Oracle Password Sync Skipped",
            message=f"Company not found for employee {employee.name} and user {user}",
        )
        return

    frappe.enqueue(
        sync_oracle_password,
        queue="short",
        enqueue_after_commit=True,
        user=user,
        company=employee.company,
        new_password=new_password,
    )


def sync_oracle_password(user: str, company: str, new_password: str):
    con = oracle_connection(company)
    if not con:
        frappe.log_error(
            title="Oracle Password Sync Failed",
            message=f"Oracle connection information is not set for company {company} and user {user}",
        )
        return

    try:
        with con.cursor() as cur:
            cur.execute(
                f"""SELECT USER_CODE FROM RIPLRR.USER_MAST WHERE USER_CODE = '{user}'""",
            )
            if not cur.fetchall():
                frappe.log_error(
                    title="Oracle Password Sync Failed",
                    message=f"User not found in Oracle DB for user {user}",
                )
                return

            cur.execute(
                f"UPDATE RIPLRR.USER_MAST SET PASSWORD = (SELECT RIPLRR.LHS_UTILITY.GET_ENCRYPT('{new_password}') FROM DUAL), LASTUPDATE = TIMESTAMP '{str(frappe.utils.now())}' WHERE USER_CODE = '{user}'"
            )

        con.commit()
    except cx_Oracle.DatabaseError:
        con.rollback()
        frappe.log_error(frappe.get_traceback(), title="Oracle Password Sync Failed")
    except Exception:
        con.rollback()
        frappe.log_error(frappe.get_traceback(), title="Oracle Password Sync Failed")
    finally:
        con.close()


@frappe.whitelist(allow_guest=True, methods=["POST"])
def update_user_password(
    new_password: str, logout_all_sessions: int = 0, key: str | None = None, old_password: str | None = None
):
    res = _get_user_for_update_password(key, old_password)
    if res.get("message"):
        frappe.local.response.http_status_code = 410
        return res["message"]

    user = res["user"]

    response = _update_password(new_password, logout_all_sessions, key, old_password)

    # Temporarily disable Oracle password sync and let Frappe handle
    # password reset with its default behavior.
    # if user != "Administrator":
    #     enqueue_oracle_password_sync(user, new_password)

    return response
