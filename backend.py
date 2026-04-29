import os
import sqlite3
from datetime import datetime, timedelta, timezone

from flask import Flask, g, jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash


DATABASE = os.environ.get("DATABASE_PATH", "/data/todos.db")
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
TOKEN_MAX_AGE_SECONDS = int(os.environ.get("TOKEN_MAX_AGE_SECONDS", "86400"))
REMINDER_WINDOW_HOURS = int(os.environ.get("REMINDER_WINDOW_HOURS", "24"))

app = Flask(__name__)
serializer = URLSafeTimedSerializer(SECRET_KEY)


def get_db():
    if "db" not in g:
        db_dir = os.path.dirname(DATABASE)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
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
    init_db()


def now_utc():
    return datetime.now(timezone.utc)


def parse_due_date(value):
    if not value:
        return None

    value = value.strip()
    formats = ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d")
    for fmt in formats:
        try:
            parsed = datetime.strptime(value, fmt)
            if fmt == "%Y-%m-%d":
                parsed = parsed.replace(hour=23, minute=59)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError("Use YYYY-MM-DD or YYYY-MM-DD HH:MM for due dates.")


def task_to_dict(row):
    due_value = row["due_date"]
    due_at = datetime.fromisoformat(due_value) if due_value else None
    reminder = "none"

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
    return serializer.dumps({"user_id": user_id})


def current_user_id():
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
    user_id = current_user_id()
    if not user_id:
        return None, (jsonify({"error": "Authentication required."}), 401)
    return user_id, None


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/api/register")
def register():
    data = request.get_json(silent=True) or request.form
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if len(username) < 3 or len(password) < 6:
        return jsonify({"error": "Username must be at least 3 characters and password at least 6."}), 400

    db = get_db()
    try:
        cursor = db.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (username, generate_password_hash(password), now_utc().isoformat()),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "That username is already taken."}), 409

    return jsonify({"token": make_token(cursor.lastrowid), "username": username}), 201


@app.post("/api/login")
def login():
    data = request.get_json(silent=True) or request.form
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    user = get_db().execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid username or password."}), 401

    return jsonify({"token": make_token(user["id"]), "username": user["username"]})


@app.get("/api/tasks")
def list_tasks():
    user_id, error = require_user()
    if error:
        return error

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
    return jsonify(task_to_dict(row)), 201


@app.post("/api/tasks/<int:task_id>/done")
def mark_done(task_id):
    user_id, error = require_user()
    if error:
        return error

    get_db().execute(
        "UPDATE tasks SET status = 'done', completed_at = ? WHERE id = ? AND user_id = ?",
        (now_utc().isoformat(), task_id, user_id),
    )
    get_db().commit()
    return jsonify({"status": "done"})


@app.delete("/api/tasks/<int:task_id>")
def delete_task(task_id):
    user_id, error = require_user()
    if error:
        return error

    get_db().execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id))
    get_db().commit()
    return jsonify({"status": "deleted"})


@app.get("/api/reminders")
def reminders():
    user_id, error = require_user()
    if error:
        return error

    rows = get_db().execute(
        "SELECT * FROM tasks WHERE user_id = ? AND status != 'done'",
        (user_id,),
    ).fetchall()
    active = [task for task in (task_to_dict(row) for row in rows) if task["reminder"] != "none"]
    return jsonify(active)


if __name__ == "__main__":
    app.run("0.0.0.0", port=5001)
