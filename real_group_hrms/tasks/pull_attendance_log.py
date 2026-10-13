import frappe
import psycopg
from frappe import _SingleDocument
from frappe.model.document import bulk_insert


def pull_data_from_postgre():
    settings: _SingleDocument = frappe.get_doc("Real Group Settings")

    if not settings.time_pro_database or not settings.time_pro_password:
        return

    conninfo = (
        f"dbname={settings.time_pro_database} "
        f"user={settings.time_pro_user} "
        f"password={settings.get_password('time_pro_password')} "
        f"host={settings.time_pro_host} "
        f"port={settings.time_pro_port}"
    )

    with psycopg.connect(conninfo, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TIME ZONE 'Asia/Kolkata'")
            cur.execute(
                """
                SELECT
                     tr.id time_pro_reference_id,
                     tr.punch_time,
                     tr.emp_code employee_id,
                     tr.punch_time::date punch_date,
                     tr.punch_time::time punch_time1,
                     tr.area_alias area,
                     (SELECT punch_direction FROM iclock_terminal t WHERE t.id = tr.terminal_id) punch_direction,
                     tr.punch_state terminal_id,
                     'N' is_processed,
                     tr.upload_time
                FROM iclock_transaction tr
                WHERE tr.upload_time > %s
                ORDER BY tr.upload_time ASC
                LIMIT 1000
            """,
                (settings.time_pro_last_sync_on,),
            )

            rows = cur.fetchall()
            result = [dict((cur.description[i][0], val) for i, val in enumerate(row)) for row in rows]
    try:
        docs = []
        for r in result:
            doc = frappe.get_doc(
                {
                    "doctype": "bioattendancelog",
                    "time_pro_reference_id": r.get("time_pro_reference_id"),
                    "employee": r.get("employee_id"),
                    "punch_date": r.get("punch_date"),
                    "punch_time": str(r.get("punch_time1")),
                    "punch_datetime": r.get("punch_datetime"),
                    "area": r.get("area"),
                    "punch_direction": r.get("punch_direction"),
                    "terminal_id": r.get("terminal_id"),
                    "is_processed": r.get("is_processed"),
                }
            )
            docs.append(doc)

            if docs:
                bulk_insert("bioattendancelog", docs)

            last_sync = result and result[-1].get("upload_time")
            settings.db_set("last_attendance_log_sync_datetime", last_sync, commit=True)

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Error while pulling attendance log from timepro")
