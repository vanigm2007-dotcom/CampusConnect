"""
db_setup.py
-----------
Creates the new tables and adds the new columns that the
new features need. It is safe to run many times: it only adds
what is missing and never deletes anything.

app.py runs this automatically when the app starts.
You can also run it by hand:   python db_setup.py
"""

import os

import mysql.connector
from dotenv import load_dotenv


# Columns that must exist in the notice tables.
# organization_admin_id = which organization owns the notice
# (NULL means it was published by the Super Admin).
NEW_COLUMNS = [
    ("events", "organization_admin_id", "INT NULL"),
    ("academic_notices", "organization_admin_id", "INT NULL"),
    ("announcements", "organization_admin_id", "INT NULL"),
]

NEW_TABLES = {
    "event_registrations": """
        CREATE TABLE IF NOT EXISTS event_registrations (
            id INT AUTO_INCREMENT PRIMARY KEY,
            event_id INT NOT NULL,
            student_id INT NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'registered',
            qr_token VARCHAR(64) NOT NULL,
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            cancelled_at DATETIME NULL,
            attended_at DATETIME NULL,
            verified_by VARCHAR(150) NULL,
            UNIQUE KEY uq_event_student (event_id, student_id),
            UNIQUE KEY uq_qr_token (qr_token),
            KEY idx_reg_student (student_id)
        )
    """,
    "event_bookmarks": """
        CREATE TABLE IF NOT EXISTS event_bookmarks (
            id INT AUTO_INCREMENT PRIMARY KEY,
            student_id INT NOT NULL,
            event_id INT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_student_event (student_id, event_id)
        )
    """,
    "notifications": """
        CREATE TABLE IF NOT EXISTS notifications (
            id INT AUTO_INCREMENT PRIMARY KEY,
            student_id INT NOT NULL,
            notif_type VARCHAR(30) NOT NULL,
            title VARCHAR(200) NOT NULL,
            message VARCHAR(500),
            link VARCHAR(300),
            is_read TINYINT(1) NOT NULL DEFAULT 0,
            dedupe_key VARCHAR(100) NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_notif_dedupe (student_id, dedupe_key),
            KEY idx_notif_student (student_id, is_read)
        )
    """,
}


def column_exists(cursor, table, column):
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND COLUMN_NAME = %s
        """,
        (table, column)
    )
    return cursor.fetchone()[0] > 0


def ensure_schema(connection=None):
    """Add anything that is missing. Returns True if all went well."""
    own_connection = connection is None

    if own_connection:
        connection = mysql.connector.connect(
            host=os.getenv("DB_HOST"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME")
        )

    cursor = connection.cursor()
    all_ok = True

    try:
        for table, column, definition in NEW_COLUMNS:
            try:
                if not column_exists(cursor, table, column):
                    cursor.execute(
                        f"ALTER TABLE {table} "
                        f"ADD COLUMN {column} {definition}"
                    )
                    print(f"[db_setup] added {table}.{column}")
            except mysql.connector.Error as error:
                all_ok = False
                print(f"[db_setup] could not add {table}.{column}: {error}")

        for name, create_sql in NEW_TABLES.items():
            try:
                cursor.execute(create_sql)
            except mysql.connector.Error as error:
                all_ok = False
                print(f"[db_setup] could not create {name}: {error}")

        connection.commit()
    finally:
        cursor.close()
        if own_connection:
            connection.close()

    return all_ok


if __name__ == "__main__":
    load_dotenv(
        dotenv_path=os.path.join(
            os.path.dirname(os.path.abspath(__file__)), ".env"
        ),
        override=True
    )

    if ensure_schema():
        print("Database is ready.")
    else:
        print("Some steps failed. Read the messages above.")
