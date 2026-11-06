from dotenv import load_dotenv
import io
import os
import re
import secrets
import uuid
from datetime import date, timedelta
from functools import wraps
from urllib.parse import urlparse

import mysql.connector

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, send_from_directory,
    send_file, abort, g
)

from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

from db_setup import ensure_schema


# --------------------------------------------------
# 1. APP CONFIGURATION
# --------------------------------------------------

load_dotenv(
    dotenv_path=os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        ".env"
    ),
    override=True
)

app = Flask(__name__)

app.secret_key = os.getenv(
    "SECRET_KEY",
    "temporary-development-key"
)

app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB

UPLOAD_FOLDER = os.path.join(app.root_path, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

ALLOWED_EXTENSIONS = {"pdf"}

# notice type (used in URLs and forms) -> database table
NOTICE_TABLES = {
    "event": "events",
    "academic": "academic_notices",
    "announcement": "announcements"
}


# --------------------------------------------------
# 2. DATABASE CONNECTION
# --------------------------------------------------

def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME")
    )


def run_query(sql, params=(), fetch="all"):
    """Run one SELECT and return the rows (or one row with fetch='one')."""
    connection = get_db_connection()
    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(sql, params)

        if fetch == "one":
            return cursor.fetchone()

        return cursor.fetchall()

    finally:
        if cursor:
            cursor.close()
        connection.close()


# Make sure the new tables and columns exist (safe to repeat).
try:
    ensure_schema()
except Exception as setup_error:
    print("Database setup problem:", setup_error)


# --------------------------------------------------
# 3. HELPER FUNCTIONS
# --------------------------------------------------

def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def get_records(table_name, include_expired=True, owner_id=None):
    """Get notices. owner_id limits them to one organization."""
    allowed_tables = set(NOTICE_TABLES.values())

    if table_name not in allowed_tables:
        raise ValueError("Invalid table name")

    conditions = []
    params = []

    if not include_expired:
        conditions.append("(expires_on IS NULL OR expires_on >= CURDATE())")

    if owner_id is not None:
        conditions.append("organization_admin_id = %s")
        params.append(owner_id)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    return run_query(
        f"SELECT * FROM {table_name} {where} ORDER BY created_at DESC",
        tuple(params)
    )


def get_events_with_counts(owner_id=None):
    """Events plus how many students registered / attended."""
    where = ""
    params = ()

    if owner_id is not None:
        where = "WHERE e.organization_admin_id = %s"
        params = (owner_id,)

    return run_query(
        f"""
        SELECT e.*,
            (SELECT COUNT(*) FROM event_registrations r
              WHERE r.event_id = e.id
                AND r.status IN ('registered', 'attended'))
                AS registered_count,
            (SELECT COUNT(*) FROM event_registrations r
              WHERE r.event_id = e.id
                AND r.status = 'attended')
                AS attended_count
        FROM events e
        {where}
        ORDER BY e.created_at DESC
        """,
        params
    )


def admin_required():
    return session.get("admin_logged_in") is True


def organization_required():
    return session.get("organization_admin_id") is not None


def safe_next_url(target):
    """Only allow links inside this website (blocks redirects elsewhere)."""
    if not target:
        return None

    parts = urlparse(target)

    if (
        parts.scheme
        or parts.netloc
        or not target.startswith("/")
        or target.startswith("//")
        or "\\" in target
    ):
        return None

    return target


def login_next_for_request():
    """Where to come back to after logging in."""
    if request.method == "GET":
        return request.full_path.rstrip("?")

    if request.referrer:
        return safe_next_url(urlparse(request.referrer).path)

    return None


def registration_closed_reason(event):
    """Return a message if students can no longer register, else None."""
    today = date.today()

    if event.get("expires_on") and event["expires_on"] < today:
        return "This event has expired."

    if event.get("event_date") and event["event_date"] < today:
        return "This event has already taken place."

    return None


def create_notification(cursor, student_id, notif_type, title,
                        message, link=None, dedupe_key=None):
    """Save a notification. The same dedupe_key is saved only once."""
    cursor.execute(
        """
        INSERT IGNORE INTO notifications
        (student_id, notif_type, title, message, link, dedupe_key)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            student_id, notif_type, title[:200],
            (message or "")[:500], link, dedupe_key
        )
    )


def generate_event_reminders(student_id):
    """Reminders for registered events happening today or in 2 days."""
    today = date.today()

    rows = run_query(
        """
        SELECT r.id AS reg_id, e.id AS event_id, e.title,
               e.event_date, e.event_time, e.venue
        FROM event_registrations r
        JOIN events e ON e.id = r.event_id
        WHERE r.student_id = %s
          AND r.status = 'registered'
          AND e.event_date BETWEEN %s AND %s
        """,
        (student_id, today, today + timedelta(days=2))
    )

    if not rows:
        return

    connection = get_db_connection()
    cursor = None

    try:
        cursor = connection.cursor()

        for row in rows:
            days_left = (row["event_date"] - today).days

            if days_left == 0:
                when = "today"
                bucket = "today"
            elif days_left == 1:
                when = "tomorrow"
                bucket = "soon"
            else:
                when = f"in {days_left} days"
                bucket = "soon"

            details = []
            if row["event_time"]:
                details.append(f"at {row['event_time']}")
            if row["venue"]:
                details.append(f"in {row['venue']}")

            message = f"{row['title']} is {when}"
            if details:
                message += " " + " ".join(details)
            message += ". Keep your QR pass ready."

            create_notification(
                cursor,
                student_id,
                "reminder",
                f"Reminder: {row['title']}",
                message,
                url_for("registration_pass", reg_id=row["reg_id"]),
                f"reminder-{bucket}-{row['reg_id']}-{row['event_date']}"
            )

        connection.commit()

    finally:
        if cursor:
            cursor.close()
        connection.close()


def build_verify_url(token):
    """The link stored inside the QR code."""
    path = url_for("verify_attendance", token=token)
    base = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")

    if base:
        return base + path

    return request.host_url.rstrip("/") + path


def make_qr_png(text):
    import qrcode

    image = qrcode.make(text, box_size=8, border=2)
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    buffer.seek(0)
    return buffer


# --------------------------------------------------
# 3B. LOGIN CHECKS (decorators)
# --------------------------------------------------

def student_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "student_id" not in session:
            flash("Please log in as a student to continue.", "error")
            return redirect(
                url_for("student_login", next=login_next_for_request())
            )

        return view(*args, **kwargs)

    return wrapped


def organization_login_required(view):
    """Organization must be logged in AND still approved."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        organization_id = session.get("organization_admin_id")

        if not organization_id:
            flash("Please log in to access your dashboard.", "error")
            return redirect(
                url_for("organization_login", next=login_next_for_request())
            )

        organization = run_query(
            """
            SELECT id, organization_name, status
            FROM organization_admins
            WHERE id = %s
            """,
            (organization_id,),
            "one"
        )

        if not organization or organization["status"] != "approved":
            session.pop("organization_admin_id", None)
            session.pop("organization_name", None)
            flash("Your organization account is not approved.", "error")
            return redirect(url_for("organization_login"))

        g.organization = organization
        return view(*args, **kwargs)

    return wrapped


def organizer_required(view):
    """Super Admin or an approved organization (used for attendance)."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if admin_required():
            g.manager = {
                "is_admin": True,
                "org_id": None,
                "name": "Super Admin"
            }
            return view(*args, **kwargs)

        organization_id = session.get("organization_admin_id")
        organization = None

        if organization_id:
            organization = run_query(
                """
                SELECT id, organization_name, status
                FROM organization_admins
                WHERE id = %s
                """,
                (organization_id,),
                "one"
            )

        if not organization or organization["status"] != "approved":
            flash("Please log in as the event organizer.", "error")
            return redirect(
                url_for("organization_login", next=login_next_for_request())
            )

        g.manager = {
            "is_admin": False,
            "org_id": organization["id"],
            "name": organization["organization_name"]
        }
        return view(*args, **kwargs)

    return wrapped


def manager_can_manage(owner_id):
    """Super Admin manages everything; an organization only its own."""
    if g.manager["is_admin"]:
        return True

    return owner_id is not None and owner_id == g.manager["org_id"]


@app.context_processor
def inject_template_values():
    """Values every page can use (unread bell count, today's date)."""
    unread = 0
    student_id = session.get("student_id")

    if student_id:
        try:
            row = run_query(
                """
                SELECT COUNT(*) AS total
                FROM notifications
                WHERE student_id = %s AND is_read = 0
                """,
                (student_id,),
                "one"
            )
            unread = row["total"] if row else 0
        except Exception:
            unread = 0

    return {"unread_notifications": unread, "today": date.today()}


@app.before_request
def create_reminders_once_a_day():
    """Create event reminders for a logged-in student (once per day)."""
    if request.endpoint in (None, "static"):
        return

    student_id = session.get("student_id")

    if not student_id:
        return

    today_text = date.today().isoformat()

    if session.get("reminders_checked") == today_text:
        return

    try:
        generate_event_reminders(student_id)
        session["reminders_checked"] = today_text
    except Exception as error:
        print("Reminder error:", error)


# --------------------------------------------------
# 4. HOME PAGE - LATEST NOTICES
# --------------------------------------------------

@app.route("/")
def index():
    connection = get_db_connection()
    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)

        query = """
            SELECT *
            FROM (
                SELECT
                    id,
                    'Event' AS notice_type,
                    category,
                    title,
                    description,
                    event_date AS display_date,
                    created_at
                FROM events
                WHERE expires_on IS NULL OR expires_on >= CURDATE()

                UNION ALL

                SELECT
                    id,
                    'Academic' AS notice_type,
                    category,
                    title,
                    description,
                    notice_date AS display_date,
                    created_at
                FROM academic_notices
                WHERE expires_on IS NULL OR expires_on >= CURDATE()

                UNION ALL

                SELECT
                    id,
                    'Announcement' AS notice_type,
                    category,
                    title,
                    description,
                    announcement_date AS display_date,
                    created_at
                FROM announcements
                WHERE expires_on IS NULL OR expires_on >= CURDATE()
            ) AS all_notices
            ORDER BY created_at DESC
            LIMIT 6
        """

        cursor.execute(query)
        latest_notices = cursor.fetchall()

    finally:
        if cursor:
            cursor.close()
        connection.close()

    return render_template(
        "index.html",
        latest_notices=latest_notices
    )



# --------------------------------------------------
# 5. EVENTS PAGE
# --------------------------------------------------

@app.route("/events")
def events():
    student_id = session.get("student_id", 0)

    event_list = run_query(
        """
        SELECT e.*,
               r.status AS reg_status,
               (b.id IS NOT NULL) AS is_bookmarked
        FROM events e
        LEFT JOIN event_registrations r
               ON r.event_id = e.id AND r.student_id = %s
        LEFT JOIN event_bookmarks b
               ON b.event_id = e.id AND b.student_id = %s
        WHERE e.expires_on IS NULL OR e.expires_on >= %s
        ORDER BY e.created_at DESC
        """,
        (student_id, student_id, date.today())
    )

    return render_template(
        "events.html",
        events=event_list
    )


# --------------------------------------------------
# 6. EVENT DETAILS PAGE
# --------------------------------------------------

@app.route("/event/<int:event_id>")
def event_detail(event_id):
    event = run_query(
        """
        SELECT *,
               event_date AS date,
               event_time AS time
        FROM events
        WHERE id = %s
        """,
        (event_id,),
        "one"
    )

    if event is None:
        return "Event not found", 404

    registration = None
    is_bookmarked = False
    student_id = session.get("student_id")

    if student_id:
        registration = run_query(
            """
            SELECT * FROM event_registrations
            WHERE event_id = %s AND student_id = %s
            """,
            (event_id, student_id),
            "one"
        )

        is_bookmarked = run_query(
            """
            SELECT id FROM event_bookmarks
            WHERE event_id = %s AND student_id = %s
            """,
            (event_id, student_id),
            "one"
        ) is not None

    total = run_query(
        """
        SELECT COUNT(*) AS total FROM event_registrations
        WHERE event_id = %s AND status IN ('registered', 'attended')
        """,
        (event_id,),
        "one"
    )

    return render_template(
        "event_detail.html",
        event=event,
        registration=registration,
        is_bookmarked=is_bookmarked,
        registered_total=total["total"] if total else 0,
        closed_reason=registration_closed_reason(event)
    )


# --------------------------------------------------
# 7. ACADEMICS PAGE
# --------------------------------------------------

@app.route("/academics")
def academics():
    notices = get_records(
        "academic_notices",
        include_expired=False
    )

    return render_template(
        "academics.html",
        academic_notices=notices
    )


# --------------------------------------------------
# 8. ANNOUNCEMENTS PAGE
# --------------------------------------------------

@app.route("/announcements")
def announcements():
    notice_list = get_records(
        "announcements",
        include_expired=False
    )

    return render_template(
        "announcements.html",
        announcements=notice_list
    )



# --------------------------------------------------
# 9. STUDENT REGISTRATION
# --------------------------------------------------

@app.route("/student/register", methods=["GET", "POST"])
def student_register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        usn = request.form.get("usn", "").strip().upper()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not name or not usn or not email or not password:
            return render_template(
                "student_register.html",
                error="Please fill in all fields."
            )

        if len(password) < 8:
            return render_template(
                "student_register.html",
                error="Password must contain at least 8 characters."
            )

        if password != confirm_password:
            return render_template(
                "student_register.html",
                error="Passwords do not match."
            )

        password_hash = generate_password_hash(password)

        connection = None
        cursor = None

        try:
            connection = get_db_connection()
            cursor = connection.cursor()

            cursor.execute(
                """
                INSERT INTO students
                (name, usn, email, password_hash)
                VALUES (%s, %s, %s, %s)
                """,
                (name, usn, email, password_hash)
            )

            connection.commit()
            flash("Registration successful! Please log in.", "success")
            return redirect(url_for("student_login"))

        except mysql.connector.IntegrityError:
            return render_template(
                "student_register.html",
                error="This USN or email is already registered."
            )

        except mysql.connector.Error as error:
            print("Student registration database error:", error)
            return render_template(
                "student_register.html",
                error="Registration failed. Please try again."
            )

        finally:
            if cursor:
                cursor.close()
            if connection and connection.is_connected():
                connection.close()

    return render_template("student_register.html")



# --------------------------------------------------
# 10. STUDENT LOGIN
# --------------------------------------------------

@app.route("/student/login", methods=["GET", "POST"])
def student_login():
    if request.method == "POST":
        usn = request.form.get("usn", "").strip().upper()
        password = request.form.get("password", "")
        next_url = safe_next_url(request.values.get("next"))

        connection = None
        cursor = None

        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)

            cursor.execute(
                """
                SELECT id, name, usn, password_hash
                FROM students
                WHERE usn = %s
                """,
                (usn,)
            )

            student = cursor.fetchone()

            if student and check_password_hash(
                student["password_hash"], password
            ):
                session.clear()
                session["student_id"] = student["id"]
                session["student_name"] = student["name"]
                session["student_usn"] = student["usn"]

                flash("Welcome! Student login successful.", "success")
                return redirect(next_url or url_for("student_dashboard"))

            return render_template(
                "student_login.html",
                error="Invalid USN or password."
            )

        except mysql.connector.Error as error:
            print("Student login database error:", error)
            return render_template(
                "student_login.html",
                error="Unable to log in. Please try again."
            )

        finally:
            if cursor:
                cursor.close()
            if connection and connection.is_connected():
                connection.close()

    return render_template("student_login.html")


# --------------------------------------------------
# 11. STUDENT DASHBOARD
# --------------------------------------------------

@app.route("/student/dashboard")
@student_required
def student_dashboard():
    student_id = session["student_id"]
    today = date.today()

    student = run_query(
        "SELECT id, name, usn, email FROM students WHERE id = %s",
        (student_id,),
        "one"
    )

    if student is None:
        session.clear()
        flash("Please log in again.", "error")
        return redirect(url_for("student_login"))

    registrations = run_query(
        """
        SELECT r.id AS reg_id, r.status, r.registered_at, r.attended_at,
               e.id AS event_id, e.title, e.category,
               e.event_date, e.event_time, e.venue
        FROM event_registrations r
        JOIN events e ON e.id = r.event_id
        WHERE r.student_id = %s
        ORDER BY (r.status = 'cancelled'), e.event_date DESC, r.id DESC
        """,
        (student_id,)
    )

    upcoming_events = run_query(
        """
        SELECT e.*,
               r.status AS reg_status,
               (b.id IS NOT NULL) AS is_bookmarked
        FROM events e
        LEFT JOIN event_registrations r
               ON r.event_id = e.id AND r.student_id = %s
        LEFT JOIN event_bookmarks b
               ON b.event_id = e.id AND b.student_id = %s
        WHERE (e.expires_on IS NULL OR e.expires_on >= %s)
          AND e.event_date >= %s
        ORDER BY e.event_date ASC
        LIMIT 6
        """,
        (student_id, student_id, today, today)
    )

    bookmarks = run_query(
        """
        SELECT e.id, e.title, e.category, e.event_date, e.event_time,
               e.venue, r.status AS reg_status
        FROM event_bookmarks b
        JOIN events e ON e.id = b.event_id
        LEFT JOIN event_registrations r
               ON r.event_id = e.id AND r.student_id = %s
        WHERE b.student_id = %s
        ORDER BY b.created_at DESC
        """,
        (student_id, student_id)
    )

    latest_notifications = run_query(
        """
        SELECT * FROM notifications
        WHERE student_id = %s
        ORDER BY created_at DESC, id DESC
        LIMIT 3
        """,
        (student_id,)
    )

    active_count = len([
        r for r in registrations if r["status"] in ("registered", "attended")
    ])
    attended_count = len([
        r for r in registrations if r["status"] == "attended"
    ])

    return render_template(
        "student_dashboard.html",
        student=student,
        registrations=registrations,
        upcoming_events=upcoming_events,
        bookmarks=bookmarks,
        latest_notifications=latest_notifications,
        active_count=active_count,
        attended_count=attended_count
    )


# --------------------------------------------------
# 11B. STUDENT: REGISTER, CANCEL, BOOKMARK
# --------------------------------------------------

@app.route("/event/<int:event_id>/register", methods=["POST"])
@student_required
def register_for_event(event_id):
    student_id = session["student_id"]
    detail_page = redirect(url_for("event_detail", event_id=event_id))

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("SELECT * FROM events WHERE id = %s", (event_id,))
        event = cursor.fetchone()

        if event is None:
            flash("Event not found.", "error")
            return redirect(url_for("events"))

        reason = registration_closed_reason(event)
        if reason:
            flash(reason + " Registration is closed.", "error")
            return detail_page

        cursor.execute(
            """
            SELECT id, status FROM event_registrations
            WHERE event_id = %s AND student_id = %s
            """,
            (event_id, student_id)
        )
        existing = cursor.fetchone()

        if existing and existing["status"] in ("registered", "attended"):
            flash("You are already registered for this event.", "error")
            return detail_page

        token = secrets.token_urlsafe(24)

        if existing:
            # The student cancelled before and is registering again.
            cursor.execute(
                """
                UPDATE event_registrations
                SET status = 'registered', qr_token = %s,
                    cancelled_at = NULL, attended_at = NULL,
                    verified_by = NULL, registered_at = NOW()
                WHERE id = %s AND status = 'cancelled'
                """,
                (token, existing["id"])
            )

            if cursor.rowcount == 0:
                flash("You are already registered for this event.", "error")
                return detail_page

            reg_id = existing["id"]

        else:
            cursor.execute(
                """
                INSERT INTO event_registrations
                (event_id, student_id, status, qr_token)
                VALUES (%s, %s, 'registered', %s)
                """,
                (event_id, student_id, token)
            )
            reg_id = cursor.lastrowid

        create_notification(
            cursor,
            student_id,
            "registration",
            "Registration confirmed",
            f"You are registered for {event['title']}. "
            "Show your QR pass at the event for attendance.",
            url_for("registration_pass", reg_id=reg_id)
        )

        connection.commit()
        flash("Registration successful! Your QR pass is ready.", "success")
        return redirect(url_for("registration_pass", reg_id=reg_id))

    except mysql.connector.IntegrityError:
        # Two clicks at the same time: the database blocks the duplicate.
        if connection:
            connection.rollback()
        flash("You are already registered for this event.", "error")
        return detail_page

    except mysql.connector.Error as error:
        if connection:
            connection.rollback()
        print("Event registration error:", error)
        flash("Could not register. Please try again.", "error")
        return detail_page

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


@app.route("/event/<int:event_id>/cancel", methods=["POST"])
@student_required
def cancel_registration(event_id):
    student_id = session["student_id"]
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            UPDATE event_registrations
            SET status = 'cancelled', cancelled_at = NOW()
            WHERE event_id = %s AND student_id = %s
              AND status = 'registered'
            """,
            (event_id, student_id)
        )

        if cursor.rowcount == 0:
            flash(
                "There is no active registration to cancel.", "error"
            )
        else:
            cursor.execute(
                "SELECT title FROM events WHERE id = %s", (event_id,)
            )
            event = cursor.fetchone()
            title = event["title"] if event else "the event"

            create_notification(
                cursor,
                student_id,
                "registration",
                "Registration cancelled",
                f"Your registration for {title} was cancelled.",
                url_for("event_detail", event_id=event_id)
            )
            connection.commit()
            flash("Your registration was cancelled.", "success")

    except mysql.connector.Error as error:
        if connection:
            connection.rollback()
        print("Cancel registration error:", error)
        flash("Could not cancel. Please try again.", "error")

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

    return redirect(
        safe_next_url(request.form.get("next"))
        or url_for("event_detail", event_id=event_id)
    )


@app.route("/event/<int:event_id>/bookmark", methods=["POST"])
@student_required
def toggle_bookmark(event_id):
    student_id = session["student_id"]
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute("SELECT id FROM events WHERE id = %s", (event_id,))

        if cursor.fetchone() is None:
            flash("Event not found.", "error")
        else:
            cursor.execute(
                """
                DELETE FROM event_bookmarks
                WHERE student_id = %s AND event_id = %s
                """,
                (student_id, event_id)
            )

            if cursor.rowcount:
                flash("Bookmark removed.", "success")
            else:
                cursor.execute(
                    """
                    INSERT INTO event_bookmarks (student_id, event_id)
                    VALUES (%s, %s)
                    """,
                    (student_id, event_id)
                )
                flash("Event bookmarked.", "success")

            connection.commit()

    except mysql.connector.IntegrityError:
        if connection:
            connection.rollback()

    except mysql.connector.Error as error:
        if connection:
            connection.rollback()
        print("Bookmark error:", error)
        flash("Could not update the bookmark.", "error")

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

    return redirect(
        safe_next_url(request.form.get("next"))
        or url_for("event_detail", event_id=event_id)
    )


# --------------------------------------------------
# 11C. STUDENT: QR PASS AND NOTIFICATIONS
# --------------------------------------------------

def get_own_registration(reg_id):
    return run_query(
        """
        SELECT r.*, e.title, e.category, e.event_date, e.event_time,
               e.venue, e.organizer, s.name AS student_name,
               s.usn AS student_usn
        FROM event_registrations r
        JOIN events e ON e.id = r.event_id
        JOIN students s ON s.id = r.student_id
        WHERE r.id = %s AND r.student_id = %s
        """,
        (reg_id, session["student_id"]),
        "one"
    )


@app.route("/registration/<int:reg_id>")
@student_required
def registration_pass(reg_id):
    registration = get_own_registration(reg_id)

    if registration is None:
        flash("Registration not found.", "error")
        return redirect(url_for("student_dashboard"))

    if registration["status"] == "cancelled":
        flash("This registration was cancelled, so it has no QR pass.", "error")
        return redirect(
            url_for("event_detail", event_id=registration["event_id"])
        )

    return render_template(
        "registration_pass.html",
        registration=registration
    )


@app.route("/registration/<int:reg_id>/qr.png")
@student_required
def registration_qr(reg_id):
    registration = get_own_registration(reg_id)

    if registration is None or registration["status"] == "cancelled":
        abort(404)

    try:
        buffer = make_qr_png(build_verify_url(registration["qr_token"]))
    except ImportError:
        return (
            "QR library missing. Run: pip install qrcode[pil]",
            500
        )

    response = send_file(buffer, mimetype="image/png")
    response.headers["Cache-Control"] = "private, no-store"
    return response


@app.route("/student/notifications")
@student_required
def student_notifications():
    student_id = session["student_id"]

    notifications = run_query(
        """
        SELECT * FROM notifications
        WHERE student_id = %s
        ORDER BY created_at DESC, id DESC
        LIMIT 100
        """,
        (student_id,)
    )

    connection = get_db_connection()
    cursor = None

    try:
        cursor = connection.cursor()
        cursor.execute(
            "UPDATE notifications SET is_read = 1 WHERE student_id = %s",
            (student_id,)
        )
        connection.commit()
    finally:
        if cursor:
            cursor.close()
        connection.close()

    return render_template(
        "student_notifications.html",
        notifications=notifications
    )


# --------------------------------------------------
# 12. ORGANIZATION ADMIN REGISTRATION
# --------------------------------------------------

@app.route("/organization/register", methods=["GET", "POST"])
def organization_register():
    if request.method == "POST":
        organization_name = request.form.get(
            "organization_name", ""
        ).strip()

        organization_type = request.form.get(
            "organization_type", ""
        ).strip()

        contact_person = request.form.get(
            "contact_person", ""
        ).strip()

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not all([
            organization_name,
            organization_type,
            contact_person,
            email,
            password
        ]):
            return render_template(
                "organization_register.html",
                error="Please fill in all fields."
            )

        if len(password) < 8:
            return render_template(
                "organization_register.html",
                error="Password must contain at least 8 characters."
            )

        if password != confirm_password:
            return render_template(
                "organization_register.html",
                error="Passwords do not match."
            )

        password_hash = generate_password_hash(password)

        connection = None
        cursor = None

        try:
            connection = get_db_connection()
            cursor = connection.cursor()

            cursor.execute(
                """
                INSERT INTO organization_admins
                (
                    organization_name,
                    organization_type,
                    contact_person,
                    email,
                    password_hash,
                    status
                )
                VALUES (%s, %s, %s, %s, %s, 'pending')
                """,
                (
                    organization_name,
                    organization_type,
                    contact_person,
                    email,
                    password_hash
                )
            )

            connection.commit()

            flash(
                "Registration request submitted! "
                "Please wait for Super Admin approval.",
                "success"
            )

            return redirect(url_for("index"))

        except mysql.connector.IntegrityError:
            return render_template(
                "organization_register.html",
                error="This email is already registered."
            )

        except mysql.connector.Error as error:
            if connection:
                connection.rollback()

            print("Organization registration error:", error)

            return render_template(
                "organization_register.html",
                error="Registration failed. Please try again."
            )

        finally:
            if cursor:
                cursor.close()
            if connection and connection.is_connected():
                connection.close()

    return render_template("organization_register.html")



# --------------------------------------------------
# 13. ORGANIZATION ADMIN LOGIN
# --------------------------------------------------

@app.route("/organization/login", methods=["GET", "POST"])
def organization_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        next_url = safe_next_url(request.values.get("next"))

        connection = None
        cursor = None

        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)

            cursor.execute(
                """
                SELECT *
                FROM organization_admins
                WHERE email = %s
                """,
                (email,)
            )

            organization = cursor.fetchone()

            if not organization or not check_password_hash(
                organization["password_hash"], password
            ):
                return render_template(
                    "organisation_login.html",
                    error="Invalid email or password."
                )

            # Only explicitly approved accounts may sign in.
            if organization["status"] != "approved":
                if organization["status"] == "pending":
                    message = (
                        "Your request is awaiting Super Admin approval."
                    )
                else:
                    message = (
                        "Your registration request was rejected."
                    )

                return render_template(
                    "organisation_login.html",
                    error=message
                )

            session.clear()
            session["organization_admin_id"] = organization["id"]
            session["organization_name"] = organization["organization_name"]

            flash("Organization login successful!", "success")
            return redirect(next_url or url_for("organization_dashboard"))

        except mysql.connector.Error as error:
            print("Organization login error:", error)
            return render_template(
                "organisation_login.html",
                error="Unable to log in. Please try again."
            )

        finally:
            if cursor:
                cursor.close()
            if connection and connection.is_connected():
                connection.close()

    return render_template("organisation_login.html")


# --------------------------------------------------
# 14. SHARED NOTICE FUNCTIONS (publish / edit / delete)
#     Used by the Super Admin and by organizations.
#     owner_id = organization id. None means Super Admin
#     (no limit). An organization can only touch rows
#     where organization_admin_id equals its own id.
# --------------------------------------------------

def publish_notice_from_form(owner_id=None, owner_name=None):
    """Save a new notice. Returns (True/False, message)."""
    page_type = request.form.get("page_type")

    title = request.form.get("title", "").strip()
    category = request.form.get("category", "").strip()
    description = request.form.get("description", "").strip()

    if not title or not category or not description:
        return False, "Please fill in all required fields."

    if page_type not in NOTICE_TABLES:
        return False, "Please select a valid notice type."

    expires_on = request.form.get("expires_on") or None
    saved_file = None
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        if page_type == "event":
            organizer = request.form.get("organizer", "").strip()

            cursor.execute(
                """
                INSERT INTO events
                (
                    title, category, description, event_date,
                    event_time, venue, organizer, eligibility,
                    registration_link, expires_on, organization_admin_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    title, category, description,
                    request.form.get("event_date") or None,
                    request.form.get("event_time"),
                    request.form.get("venue"),
                    organizer or owner_name,
                    request.form.get("eligibility"),
                    request.form.get("registration_link"),
                    expires_on, owner_id
                )
            )

        elif page_type == "academic":
            uploaded_file = request.files.get("attachment")

            if uploaded_file and uploaded_file.filename:
                if not allowed_file(uploaded_file.filename):
                    return False, "Only PDF files are allowed."

                original_name = secure_filename(uploaded_file.filename)
                saved_file = f"{uuid.uuid4().hex}_{original_name}"

                uploaded_file.save(
                    os.path.join(app.config["UPLOAD_FOLDER"], saved_file)
                )

            cursor.execute(
                """
                INSERT INTO academic_notices
                (
                    title, category, description, notice_date,
                    file_path, expires_on, organization_admin_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    title, category, description,
                    request.form.get("notice_date") or None,
                    saved_file, expires_on, owner_id
                )
            )

        else:
            cursor.execute(
                """
                INSERT INTO announcements
                (
                    title, category, description,
                    announcement_date, expires_on, organization_admin_id
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    title, category, description,
                    request.form.get("announcement_date") or None,
                    expires_on, owner_id
                )
            )

        connection.commit()
        return True, "Notice published successfully!"

    except Exception as error:
        if connection:
            connection.rollback()

        if saved_file:
            pdf_path = os.path.join(app.config["UPLOAD_FOLDER"], saved_file)
            if os.path.isfile(pdf_path):
                os.remove(pdf_path)

        print("Publish error:", error)
        return False, "Could not publish the notice. Check the server terminal."

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


def edit_notice_flow(notice_type, notice_id, owner_id,
                     edit_endpoint, back_endpoint):
    table_name = NOTICE_TABLES.get(notice_type)

    if not table_name:
        flash("Invalid notice type.", "error")
        return redirect(url_for(back_endpoint))

    owner_sql = ""
    owner_params = ()

    if owner_id is not None:
        owner_sql = " AND organization_admin_id = %s"
        owner_params = (owner_id,)

    connection = None
    cursor = None
    new_file_path = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            f"SELECT * FROM {table_name} WHERE id = %s{owner_sql}",
            (notice_id,) + owner_params
        )

        notice = cursor.fetchone()

        if not notice:
            flash("Notice not found, or it does not belong to you.", "error")
            return redirect(url_for(back_endpoint))

        if request.method == "POST":
            title = request.form.get("title", "").strip()
            category = request.form.get("category", "").strip()
            description = request.form.get("description", "").strip()

            if not title or not category or not description:
                flash("Please fill in all required fields.", "error")
                return redirect(
                    url_for(
                        edit_endpoint,
                        notice_type=notice_type,
                        notice_id=notice_id
                    )
                )

            expires_on = request.form.get("expires_on")
            if expires_on == "":
                expires_on = None
            if expires_on is None:
                expires_on = notice.get("expires_on")

            where_params = (notice_id,) + owner_params

            if notice_type == "event":
                cursor.execute(
                    f"""
                    UPDATE events
                    SET title = %s,
                        category = %s,
                        description = %s,
                        event_date = %s,
                        event_time = %s,
                        venue = %s,
                        organizer = %s,
                        eligibility = %s,
                        registration_link = %s,
                        expires_on = %s
                    WHERE id = %s{owner_sql}
                    """,
                    (
                        title,
                        category,
                        description,
                        request.form.get("event_date") or None,
                        request.form.get("event_time"),
                        request.form.get("venue"),
                        request.form.get("organizer"),
                        request.form.get("eligibility"),
                        request.form.get("registration_link"),
                        expires_on
                    ) + where_params
                )

            elif notice_type == "academic":
                uploaded_file = request.files.get("attachment")
                file_path = notice.get("file_path")

                if uploaded_file and uploaded_file.filename:
                    if not allowed_file(uploaded_file.filename):
                        flash("Only PDF files are allowed.", "error")
                        return redirect(
                            url_for(
                                edit_endpoint,
                                notice_type=notice_type,
                                notice_id=notice_id
                            )
                        )

                    original_name = secure_filename(uploaded_file.filename)
                    new_file_path = f"{uuid.uuid4().hex}_{original_name}"

                    uploaded_file.save(
                        os.path.join(
                            app.config["UPLOAD_FOLDER"], new_file_path
                        )
                    )

                    file_path = new_file_path

                cursor.execute(
                    f"""
                    UPDATE academic_notices
                    SET title = %s,
                        category = %s,
                        description = %s,
                        notice_date = %s,
                        file_path = %s,
                        expires_on = %s
                    WHERE id = %s{owner_sql}
                    """,
                    (
                        title,
                        category,
                        description,
                        request.form.get("notice_date") or None,
                        file_path,
                        expires_on
                    ) + where_params
                )

            else:
                cursor.execute(
                    f"""
                    UPDATE announcements
                    SET title = %s,
                        category = %s,
                        description = %s,
                        announcement_date = %s,
                        expires_on = %s
                    WHERE id = %s{owner_sql}
                    """,
                    (
                        title,
                        category,
                        description,
                        request.form.get("announcement_date") or None,
                        expires_on
                    ) + where_params
                )

            connection.commit()

            if (
                notice_type == "academic"
                and new_file_path
                and notice.get("file_path")
            ):
                old_pdf = os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    os.path.basename(notice["file_path"])
                )

                if os.path.isfile(old_pdf):
                    os.remove(old_pdf)

            flash("Notice updated successfully!", "success")
            return redirect(url_for(back_endpoint))

        return render_template(
            "edit_notice.html",
            notice=notice,
            notice_type=notice_type,
            back_url=url_for(back_endpoint)
        )

    except Exception as error:
        if connection:
            connection.rollback()

        if new_file_path:
            new_pdf = os.path.join(
                app.config["UPLOAD_FOLDER"], new_file_path
            )

            if os.path.isfile(new_pdf):
                os.remove(new_pdf)

        print("Notice editing error:", error)
        flash("Could not edit the notice.", "error")
        return redirect(url_for(back_endpoint))

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


def delete_notice_flow(notice_type, notice_id, owner_id, back_endpoint):
    table_name = NOTICE_TABLES.get(notice_type)

    if not table_name:
        flash("Invalid notice type.", "error")
        return redirect(url_for(back_endpoint))

    owner_sql = ""
    params = (notice_id,)

    if owner_id is not None:
        owner_sql = " AND organization_admin_id = %s"
        params = (notice_id, owner_id)

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        file_path = None

        if notice_type == "academic":
            cursor.execute(
                f"SELECT file_path FROM academic_notices "
                f"WHERE id = %s{owner_sql}",
                params
            )
            result = cursor.fetchone()

            if result:
                file_path = result[0]

        cursor.execute(
            f"DELETE FROM {table_name} WHERE id = %s{owner_sql}",
            params
        )

        if cursor.rowcount == 0:
            flash("Notice not found, or it does not belong to you.", "error")
        else:
            if notice_type == "event":
                # Remove everything that belonged to this event.
                cursor.execute(
                    "DELETE FROM event_registrations WHERE event_id = %s",
                    (notice_id,)
                )
                cursor.execute(
                    "DELETE FROM event_bookmarks WHERE event_id = %s",
                    (notice_id,)
                )

            connection.commit()

            if file_path:
                pdf_path = os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    os.path.basename(file_path)
                )

                if os.path.isfile(pdf_path):
                    os.remove(pdf_path)

            flash("Notice deleted successfully.", "success")

    except Exception as error:
        if connection:
            connection.rollback()

        print("Notice deletion error:", error)
        flash("Could not delete the notice.", "error")

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

    return redirect(url_for(back_endpoint))


# --------------------------------------------------
# 14B. ORGANIZATION DASHBOARD (own notices only)
# --------------------------------------------------

@app.route("/organization/dashboard")
@organization_login_required
def organization_dashboard():
    owner_id = g.organization["id"]

    return render_template(
        "organisation_dashboard.html",
        organization_name=g.organization["organization_name"],
        events=get_events_with_counts(owner_id),
        academic_notices=get_records(
            "academic_notices", owner_id=owner_id
        ),
        announcements=get_records("announcements", owner_id=owner_id)
    )


@app.route("/organization/publish", methods=["POST"])
@organization_login_required
def organization_publish():
    ok, message = publish_notice_from_form(
        owner_id=g.organization["id"],
        owner_name=g.organization["organization_name"]
    )

    flash(message, "success" if ok else "error")
    return redirect(url_for("organization_dashboard"))


@app.route(
    "/organization/edit/<notice_type>/<int:notice_id>",
    methods=["GET", "POST"]
)
@organization_login_required
def organization_edit_notice(notice_type, notice_id):
    return edit_notice_flow(
        notice_type, notice_id, g.organization["id"],
        "organization_edit_notice", "organization_dashboard"
    )


@app.route(
    "/organization/delete/<notice_type>/<int:notice_id>",
    methods=["POST"]
)
@organization_login_required
def organization_delete_notice(notice_type, notice_id):
    return delete_notice_flow(
        notice_type, notice_id, g.organization["id"],
        "organization_dashboard"
    )


# --------------------------------------------------
# 15. ORGANIZATION ADMIN LOGOUT
# --------------------------------------------------

@app.route("/organization/logout")
def organization_logout():
    session.pop("organization_admin_id", None)
    session.pop("organization_name", None)

    flash("Organization logged out successfully.", "success")
    return redirect(url_for("index"))



# --------------------------------------------------
# 16. SUPER ADMIN LOGIN PAGE
# --------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        correct_username = os.getenv("ADMIN_USERNAME", "").strip()
        correct_password = os.getenv("ADMIN_PASSWORD", "")

        if (
            username == correct_username
            and password == correct_password
            and correct_username
            and correct_password
        ):
            session.clear()
            session["admin_logged_in"] = True

            flash("Login successful!", "success")
            return redirect(url_for("admin"))

        return render_template(
            "login.html",
            error="Invalid username or password"
        )

    return render_template("login.html")



# --------------------------------------------------
# 17. SUPER ADMIN DASHBOARD AND PUBLISH NOTICE
# --------------------------------------------------

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if not admin_required():
        return redirect(url_for("login"))

    if request.method == "POST":
        ok, message = publish_notice_from_form()
        flash(message, "success" if ok else "error")
        return redirect(url_for("admin"))

    return render_template(
        "admin.html",
        events=get_events_with_counts(),
        academic_notices=get_records("academic_notices"),
        announcements=get_records("announcements")
    )


# --------------------------------------------------
# 18. DELETE NOTICE (Super Admin)
# --------------------------------------------------

@app.route(
    "/admin/delete/<notice_type>/<int:notice_id>",
    methods=["POST"]
)
def delete_notice(notice_type, notice_id):
    if not admin_required():
        return redirect(url_for("login"))

    return delete_notice_flow(notice_type, notice_id, None, "admin")


# --------------------------------------------------
# 19. EDIT NOTICE (Super Admin)
# --------------------------------------------------

@app.route(
    "/admin/edit/<notice_type>/<int:notice_id>",
    methods=["GET", "POST"]
)
def edit_notice(notice_type, notice_id):
    if not admin_required():
        return redirect(url_for("login"))

    return edit_notice_flow(
        notice_type, notice_id, None, "edit_notice", "admin"
    )


# --------------------------------------------------
# 19B. QR ATTENDANCE (organizer side)
# --------------------------------------------------

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{20,64}")


def extract_token(text):
    """Accept a pasted link or a plain code and return the token."""
    text = (text or "").strip().split("?")[0].rstrip("/")
    candidate = text.rsplit("/", 1)[-1]

    if TOKEN_PATTERN.fullmatch(candidate):
        return candidate

    return None


@app.route("/event/<int:event_id>/attendance")
@organizer_required
def event_attendance(event_id):
    event = run_query(
        "SELECT * FROM events WHERE id = %s", (event_id,), "one"
    )

    if event is None:
        abort(404)

    if not manager_can_manage(event["organization_admin_id"]):
        flash("You can only manage attendance for your own events.", "error")
        return redirect(
            url_for("admin") if g.manager["is_admin"]
            else url_for("organization_dashboard")
        )

    participants = run_query(
        """
        SELECT r.id, r.status, r.registered_at, r.attended_at,
               s.name, s.usn, s.email
        FROM event_registrations r
        JOIN students s ON s.id = r.student_id
        WHERE r.event_id = %s
        ORDER BY (r.status = 'cancelled'), s.name
        """,
        (event_id,)
    )

    counts = {
        "registered": len([
            p for p in participants if p["status"] in ("registered", "attended")
        ]),
        "attended": len([
            p for p in participants if p["status"] == "attended"
        ]),
        "cancelled": len([
            p for p in participants if p["status"] == "cancelled"
        ])
    }

    return render_template(
        "event_attendance.html",
        event=event,
        participants=participants,
        counts=counts,
        back_url=(
            url_for("admin") if g.manager["is_admin"]
            else url_for("organization_dashboard")
        )
    )


@app.route("/attendance/lookup", methods=["POST"])
@organizer_required
def attendance_lookup():
    token = extract_token(request.form.get("code"))
    event_id = request.form.get("event_id", type=int)

    if token:
        return redirect(url_for("verify_attendance", token=token))

    flash("That code is not valid. Paste the full QR link or backup code.", "error")

    if event_id:
        return redirect(url_for("event_attendance", event_id=event_id))

    return redirect(url_for("organization_dashboard"))


def load_registration_by_token(token):
    return run_query(
        """
        SELECT r.id, r.status, r.registered_at, r.attended_at,
               r.verified_by, r.student_id, r.event_id,
               s.name AS student_name, s.usn AS student_usn,
               s.email AS student_email,
               e.title AS event_title, e.event_date, e.event_time,
               e.venue, e.organization_admin_id AS owner_id
        FROM event_registrations r
        JOIN students s ON s.id = r.student_id
        JOIN events e ON e.id = r.event_id
        WHERE r.qr_token = %s
        """,
        (token,),
        "one"
    )


def attendance_state(registration):
    if registration is None:
        return "invalid"

    if not manager_can_manage(registration["owner_id"]):
        return "forbidden"

    if registration["status"] == "attended":
        return "attended"

    if registration["status"] == "cancelled":
        return "cancelled"

    return "ready"


@app.route("/attendance/verify/<token>", methods=["GET", "POST"])
@organizer_required
def verify_attendance(token):
    registration = load_registration_by_token(token)
    state = attendance_state(registration)

    if request.method == "POST":
        if state == "ready":
            connection = get_db_connection()
            cursor = None

            try:
                cursor = connection.cursor()

                # status = 'registered' in WHERE means a code can be
                # used only once, even if two people scan at once.
                cursor.execute(
                    """
                    UPDATE event_registrations
                    SET status = 'attended', attended_at = NOW(),
                        verified_by = %s
                    WHERE qr_token = %s AND status = 'registered'
                    """,
                    (g.manager["name"], token)
                )

                if cursor.rowcount == 1:
                    create_notification(
                        cursor,
                        registration["student_id"],
                        "attendance",
                        "Attendance marked",
                        f"Your attendance for {registration['event_title']} "
                        "has been recorded.",
                        url_for(
                            "event_detail",
                            event_id=registration["event_id"]
                        )
                    )
                    flash(
                        f"Attendance marked for "
                        f"{registration['student_name']}.",
                        "success"
                    )

                connection.commit()

            except mysql.connector.Error as error:
                connection.rollback()
                print("Attendance error:", error)
                flash("Could not mark attendance.", "error")

            finally:
                if cursor:
                    cursor.close()
                connection.close()

        return redirect(url_for("verify_attendance", token=token))

    return render_template(
        "attendance_verify.html",
        registration=registration,
        state=state,
        token=token
    )


# --------------------------------------------------
# 20. PDF DOWNLOAD / VIEW
# --------------------------------------------------

@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        filename
    )



# --------------------------------------------------
# 21. STUDENT LOGOUT
# --------------------------------------------------

@app.route("/student/logout")
def student_logout():
    session.pop("student_id", None)
    session.pop("student_name", None)
    session.pop("student_usn", None)
    session.pop("reminders_checked", None)

    flash("You have been logged out successfully.", "success")
    return redirect(url_for("student_login"))


# --------------------------------------------------
# 22. SUPER ADMIN LOGOUT
# --------------------------------------------------

@app.route("/logout")
def logout():
    session.pop("admin_logged_in", None)

    flash("You have been logged out.", "success")
    return redirect(url_for("index"))



# --------------------------------------------------
# 23. FILE SIZE ERROR
# --------------------------------------------------

@app.errorhandler(413)
def file_too_large(error):
    flash(
        "File is too large. Maximum size is 10 MB.",
        "error"
    )

    if admin_required():
        return redirect(url_for("admin"))

    if organization_required():
        return redirect(url_for("organization_dashboard"))

    return redirect(url_for("index"))


# --------------------------------------------------
# 24. RUN THE APPLICATION
# --------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)
