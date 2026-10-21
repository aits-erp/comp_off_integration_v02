import frappe

SOURCE_TABLE = "bio_attendance_log"
TARGET_TABLE = "tabbioattendancelog"
START_DATE = "2026-01-01"
END_DATE = "2026-01-31"


def table_exists(table_name: str) -> bool:
    try:
        frappe.db.sql(f"SELECT 1 FROM `{table_name}` LIMIT 1")
        return True
    except Exception:
        return False


def execute():
    print("[BioAttendance] Starting migration")
    print(f"[BioAttendance] Date range: {START_DATE} → {END_DATE}")

    if not table_exists(SOURCE_TABLE):
        return

    if not table_exists(TARGET_TABLE):
        return

    print("Tables exist. Running insert...")

    frappe.db.sql(
        """
        INSERT INTO `tabbioattendancelog` (
            employee_id,
            punch_date,
            punch_time,
            area,
            terminal_id,
            punch_direction,
            present_day,
            is_processed,
            time_pro_reference_id,
            message,
            punch_date_backup
        )
        SELECT
            bal.employee_id,
            bal.punch_date,
            bal.punch_time,
            bal.area,
            bal.terminal_id,
            bal.punch_direction,
            bal.present_day,
            bal.is_processed,
            bal.time_pro_reference_id,
            bal.message,
            bal.punch_date_backup
        FROM bio_attendance_log bal
        WHERE bal.employee_id IS NOT NULL
          AND bal.punch_date IS NOT NULL
          AND bal.punch_time IS NOT NULL
          AND bal.punch_date BETWEEN %s AND %s
          AND NOT EXISTS (
              SELECT 1
              FROM `tabbioattendancelog` t
              WHERE t.employee_id = bal.employee_id
                AND t.punch_date = bal.punch_date
                AND t.punch_time = bal.punch_time
          )
        """,
        (START_DATE, END_DATE),
    )

    inserted_rows = frappe.db.sql("SELECT ROW_COUNT()")[0][0]

    print("Insert completed")
    print(f"Rows inserted: {inserted_rows}")

    frappe.db.commit()
    print("Transaction committed")
