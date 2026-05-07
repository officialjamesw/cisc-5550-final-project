import os

from flask import Flask, flash, redirect, render_template, request, session, url_for
import requests

# The frontend talks to the backend through an environment variable so the same
# code works in Docker Compose, Kubernetes, and local development.
API_BASE = os.environ.get("API_BASE", "http://backend:5001")

app = Flask(__name__)
# Flask uses this key to sign browser session cookies.
app.secret_key = os.environ.get("SECRET_KEY", "frontend-dev-secret-change-me")


def api_headers():
    # The backend expects a bearer token for all task-related requests.
    token = session.get("token")
    return {"Authorization": f"Bearer {token}"} if token else {}


def api_request(method, path, **kwargs):
    # Central helper for frontend-to-backend API calls. A short timeout keeps the
    # page from hanging if the backend container is unavailable.
    try:
        return requests.request(method, f"{API_BASE}{path}", timeout=5, **kwargs)
    except requests.RequestException:
        flash("The task service is unavailable. Try again in a moment.", "danger")
        return None


def require_login():
    # Routes call this before showing or changing private task data.
    if "token" not in session:
        flash("Please log in to manage your tasks.", "info")
        return redirect(url_for("login"))
    return None

@app.route("/")
def show_list():
    redirect_response = require_login()
    if redirect_response:
        return redirect_response

    # The backend returns only the tasks that belong to the logged-in user.
    resp = api_request("GET", "/api/tasks", headers=api_headers())
    tdlist = resp.json() if resp and resp.ok else []
    # Reminder state is calculated by the backend and displayed by the frontend.
    reminders = [task for task in tdlist if task.get("reminder") != "none"]
    return render_template("index.html", todolist=tdlist, reminders=reminders, username=session.get("username"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        # Registration happens in the backend so password hashing stays in one place.
        resp = api_request("POST", "/api/register", json={
            "username": request.form["username"],
            "password": request.form["password"],
        })
        if resp and resp.ok:
            data = resp.json()
            # Store only the signed token and username in the browser session.
            session["token"] = data["token"]
            session["username"] = data["username"]
            flash("Account created. Your tasks will stay private to you.", "success")
            return redirect(url_for("show_list"))
        flash(resp.json().get("error", "Could not create account.") if resp else "Could not create account.", "danger")
    return render_template("login.html", mode="register")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        # The backend verifies the password and returns a token if login succeeds.
        resp = api_request("POST", "/api/login", json={
            "username": request.form["username"],
            "password": request.form["password"],
        })
        if resp and resp.ok:
            data = resp.json()
            session["token"] = data["token"]
            session["username"] = data["username"]
            flash("Welcome back.", "success")
            return redirect(url_for("show_list"))
        flash(resp.json().get("error", "Could not log in.") if resp else "Could not log in.", "danger")
    return render_template("login.html", mode="login")


@app.route("/logout")
def logout():
    # Clearing the session removes the backend token from the browser.
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))

@app.route("/add", methods=["POST"])
def add_entry():
    redirect_response = require_login()
    if redirect_response:
        return redirect_response

    # Tasks are created through the backend so they can be tied to the user id
    # from the authentication token.
    resp = api_request("POST", "/api/tasks", headers=api_headers(), json={
        "what_to_do": request.form["what_to_do"],
        "due_date": request.form["due_date"]
    })
    if resp and not resp.ok:
        flash(resp.json().get("error", "Could not add task."), "danger")
    return redirect(url_for("show_list"))

@app.route("/delete/<int:item_id>", methods=["POST"])
def delete_entry(item_id):
    redirect_response = require_login()
    if redirect_response:
        return redirect_response

    # Deleting by numeric id avoids exposing task text in the URL.
    api_request("DELETE", f"/api/tasks/{item_id}", headers=api_headers())
    return redirect(url_for("show_list"))

@app.route("/mark/<int:item_id>", methods=["POST"])
def mark_as_done(item_id):
    redirect_response = require_login()
    if redirect_response:
        return redirect_response

    # Completion is handled by the backend to enforce task ownership.
    api_request("POST", f"/api/tasks/{item_id}/done", headers=api_headers())
    return redirect(url_for("show_list"))

if __name__ == "__main__":
    # This is used for direct local runs. Docker uses Gunicorn from the Dockerfile.
    app.run("0.0.0.0", port=5000)
