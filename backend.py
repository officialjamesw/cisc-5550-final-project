import os
import sqlite3
import logging
from datetime import datetime, timedelta, timezone

from flask import Flask, g, jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash


# Environment variables let Docker Compose and Kubernetes provide deployment
# specific values without changing code.
DATABASE = os.environ.get("DATABASE_PATH", "/data/todos.db")
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
TOKEN_MAX_AGE_SECONDS = int(os.environ.get("TOKEN_MAX_AGE_SECONDS", "86400"))
REMINDER_WINDOW_HOURS = int(os.environ.get("REMINDER_WINDOW_HOURS", "24"))

app = Flask(__name__)
# Send INFO-level audit logs to stdout so Kubernetes can collect them.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
app.logger.setLevel(logging.INFO)
serializer = URLSafeTimedSerializer(SECRET_KEY)


def audit_log(action, username=None, user_id=None, task_id=None, task_text=None):
    # These structured log fragments make user activity easy to find with
    # `kubectl logs deployment/todo-backend`.
    parts = [
        f"audit action={action}",
        f"user_id={user_id}" if user_id is not None else None,
        f"username={username}" if username else None,
        f"task_id={task_id}" if task_id is not None else None,
        f"task={task_text!r}" if task_text else None,
    ]
    app.logger.info(" ".join(part for part in parts if part))


def get_db():
    # Flask's `g` object stores one database connection per request.
    if "db" not in g:
        db_dir = os.path.dirname(DATABASE)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_error):
    # Close the request-scoped SQLite connection after Flask finishes the request.
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    # SQLite tables are created automatically so the app can start in a fresh
    # Docker volume or Kubernetes persistent volume.
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            what_to_do TEXT NOT NULL,
            due_date TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL,
            completed_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );
        """
    )
    db.commit()


@app.before_request
def ensure_db():
    # Ensure the database schema exists before any API endpoint runs.
    init_db()


def now_utc():
    # Store times consistently in UTC to avoid server timezone surprises.
    return datetime.now(timezone.utc)


def parse_due_date(value):
    # Accept both browser datetime-local values and simpler date strings.
    if not value:
        return None

    value = value.strip()
    formats = ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d")
    for fmt in formats:
        try:
            parsed = datetime.strptime(value, fmt)
            if fmt == "%Y-%m-%d":
                # Date-only tasks are treated as due at the end of that day.
                parsed = parsed.replace(hour=23, minute=59)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError("Use YYYY-MM-DD or YYYY-MM-DD HH:MM for due dates.")


def task_to_dict(row):
    # Convert a SQLite row into the JSON shape expected by the frontend.
    due_value = row["due_date"]
    due_at = datetime.fromisoformat(due_value) if due_value else None
    reminder = "none"

    # Reminder status is calculated dynamically instead of being stored, so it
    # always reflects the current time.
    if row["status"] != "done" and due_at:
        if due_at < now_utc():
            reminder = "overdue"
        elif due_at <= now_utc() + timedelta(hours=REMINDER_WINDOW_HOURS):
            reminder = "due_soon"

    return {
        "id": row["id"],
        "what_to_do": row["what_to_do"],
        "due_date": due_value,
        "status": row["status"],
        "reminder": reminder,
        "completed_at": row["completed_at"],
    }


def make_token(user_id):
    # The token proves the user has logged in without storing password data in
    # the frontend session.
    return serializer.dumps({"user_id": user_id})


def current_user_id():
    # Read the bearer token sent by the frontend and turn it back into a user id.
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header.removeprefix("Bearer ").strip()
    try:
        payload = serializer.loads(token, max_age=TOKEN_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    return payload.get("user_id")


def require_user():
    # Shared guard for endpoints that require authentication.
    user_id = current_user_id()
    if not user_id:
        return None, (jsonify({"error": "Authentication required."}), 401)
    return user_id, None


def get_username(user_id):
    # Used only for readable audit logs.
    user = get_db().execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
    return user["username"] if user else None


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/api/register")
def register():
    data = request.get_json(silent=True) or request.form
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    # Basic validation keeps invalid accounts out before attempting the insert.
    if len(username) < 3 or len(password) < 6:
        return jsonify({"error": "Username must be at least 3 characters and password at least 6."}), 400

    db = get_db()
    try:
        # Store a password hash, never the plain-text password.
        cursor = db.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (username, generate_password_hash(password), now_utc().isoformat()),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "That username is already taken."}), 409

    audit_log("register", username=username, user_id=cursor.lastrowid)
    return jsonify({"token": make_token(cursor.lastrowid), "username": username}), 201


@app.post("/api/login")
def login():
    data = request.get_json(silent=True) or request.form
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    # Fetch the user and compare the submitted password with the stored hash.
    user = get_db().execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if not user or not check_password_hash(user["password_hash"], password):
        audit_log("login_failed", username=username)
        return jsonify({"error": "Invalid username or password."}), 401

    audit_log("login", username=user["username"], user_id=user["id"])
    return jsonify({"token": make_token(user["id"]), "username": user["username"]})


@app.get("/api/tasks")
def list_tasks():
    user_id, error = require_user()
    if error:
        return error

    # Every task query is scoped by user_id so users cannot see each other's data.
    rows = get_db().execute(
        "SELECT * FROM tasks WHERE user_id = ? ORDER BY status, due_date IS NULL, due_date, id DESC",
        (user_id,),
    ).fetchall()
    return jsonify([task_to_dict(row) for row in rows])


@app.post("/api/tasks")
def add_task():
    user_id, error = require_user()
    if error:
        return error

    data = request.get_json(silent=True) or request.form
    what_to_do = (data.get("what_to_do") or "").strip()
    if not what_to_do:
        return jsonify({"error": "Task text is required."}), 400

    # The due date is optional, but if present it must match an accepted format.
    try:
        due_at = parse_due_date(data.get("due_date") or "")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    cursor = get_db().execute(
        """
        INSERT INTO tasks (user_id, what_to_do, due_date, status, created_at)
        VALUES (?, ?, ?, 'open', ?)
        """,
        (user_id, what_to_do, due_at.isoformat() if due_at else None, now_utc().isoformat()),
    )
    get_db().commit()
    row = get_db().execute("SELECT * FROM tasks WHERE id = ?", (cursor.lastrowid,)).fetchone()
    audit_log(
        "task_created",
        username=get_username(user_id),
        user_id=user_id,
        task_id=cursor.lastrowid,
        task_text=what_to_do,
    )
    return jsonify(task_to_dict(row)), 201


@app.post("/api/tasks/<int:task_id>/done")
def mark_done(task_id):
    user_id, error = require_user()
    if error:
        return error

    # Read the task first so the audit log can include the task text.
    task = get_db().execute(
        "SELECT what_to_do FROM tasks WHERE id = ? AND user_id = ?",
        (task_id, user_id),
    ).fetchone()
    get_db().execute(
        # The WHERE clause includes user_id so one user cannot complete another
        # user's task by guessing an id.
        "UPDATE tasks SET status = 'done', completed_at = ? WHERE id = ? AND user_id = ?",
        (now_utc().isoformat(), task_id, user_id),
    )
    get_db().commit()
    if task:
        audit_log(
            "task_completed",
            username=get_username(user_id),
            user_id=user_id,
            task_id=task_id,
            task_text=task["what_to_do"],
        )
    return jsonify({"status": "done"})


@app.delete("/api/tasks/<int:task_id>")
def delete_task(task_id):
    user_id, error = require_user()
    if error:
        return error

    # Read before deleting so the audit log can describe what changed.
    task = get_db().execute(
        "SELECT what_to_do FROM tasks WHERE id = ? AND user_id = ?",
        (task_id, user_id),
    ).fetchone()
    # The user_id condition enforces ownership on delete operations.
    get_db().execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id))
    get_db().commit()
    if task:
        audit_log(
            "task_deleted",
            username=get_username(user_id),
            user_id=user_id,
            task_id=task_id,
            task_text=task["what_to_do"],
        )
    return jsonify({"status": "deleted"})


@app.get("/api/reminders")
def reminders():
    user_id, error = require_user()
    if error:
        return error

    # Return only active reminders for open tasks owned by the current user.
    rows = get_db().execute(
        "SELECT * FROM tasks WHERE user_id = ? AND status != 'done'",
        (user_id,),
    ).fetchall()
    active = [task for task in (task_to_dict(row) for row in rows) if task["reminder"] != "none"]
    return jsonify(active)


if __name__ == "__main__":
    # This is used for direct local runs. Docker uses Gunicorn from the Dockerfile.
    app.run("0.0.0.0", port=5001)
