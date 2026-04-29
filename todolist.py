import os

from flask import Flask, flash, redirect, render_template, request, session, url_for
import requests

API_BASE = os.environ.get("API_BASE", "http://backend:5001")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "frontend-dev-secret-change-me")


def api_headers():
    token = session.get("token")
    return {"Authorization": f"Bearer {token}"} if token else {}


def api_request(method, path, **kwargs):
    try:
        return requests.request(method, f"{API_BASE}{path}", timeout=5, **kwargs)
    except requests.RequestException:
        flash("The task service is unavailable. Try again in a moment.", "danger")
        return None


def require_login():
    if "token" not in session:
        flash("Please log in to manage your tasks.", "info")
        return redirect(url_for("login"))
    return None

@app.route("/")
def show_list():
    redirect_response = require_login()
    if redirect_response:
        return redirect_response

    resp = api_request("GET", "/api/tasks", headers=api_headers())
    tdlist = resp.json() if resp and resp.ok else []
    reminders = [task for task in tdlist if task.get("reminder") != "none"]
    return render_template("index.html", todolist=tdlist, reminders=reminders, username=session.get("username"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        resp = api_request("POST", "/api/register", json={
            "username": request.form["username"],
            "password": request.form["password"],
        })
        if resp and resp.ok:
            data = resp.json()
            session["token"] = data["token"]
            session["username"] = data["username"]
            flash("Account created. Your tasks will stay private to you.", "success")
            return redirect(url_for("show_list"))
        flash(resp.json().get("error", "Could not create account.") if resp else "Could not create account.", "danger")
    return render_template("login.html", mode="register")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
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
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))

@app.route("/add", methods=["POST"])
def add_entry():
    redirect_response = require_login()
    if redirect_response:
        return redirect_response

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

    api_request("DELETE", f"/api/tasks/{item_id}", headers=api_headers())
    return redirect(url_for("show_list"))

@app.route("/mark/<int:item_id>", methods=["POST"])
def mark_as_done(item_id):
    redirect_response = require_login()
    if redirect_response:
        return redirect_response

    api_request("POST", f"/api/tasks/{item_id}/done", headers=api_headers())
    return redirect(url_for("show_list"))

if __name__ == "__main__":
    app.run("0.0.0.0", port=5000)
