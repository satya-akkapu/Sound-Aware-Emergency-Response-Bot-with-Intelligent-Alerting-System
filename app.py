from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = "your_secret_key_here"

DB_PATH = "users.db"

# ================= LOCATION STORAGE =================
latest_location = {
    "lat": None,
    "lon": None
}

# ================= LISTENER STATE =================
listener_state = {
    "running": False,
    "emergency": False
}

# ================= DATABASE =================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT,
            last_name TEXT,
            email TEXT UNIQUE,
            password_hash TEXT,
            relative_phone1 TEXT,
            relative_phone2 TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ================= ROUTES =================
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/contact")
def contact():
    return render_template("contact.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        data = request.form
        if not all(data.values()):
            flash("All fields required", "error")
            return redirect(url_for("register"))

        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO users VALUES (NULL,?,?,?,?,?,?,?)
            """, (
                data["first_name"],
                data["last_name"],
                data["email"],
                generate_password_hash(data["password"]),
                data["relative_phone1"],
                data["relative_phone2"],
                datetime.now().isoformat()
            ))
            conn.commit()
            conn.close()
            flash("Registration successful", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Email already exists", "error")

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email=?", (request.form["email"],))
        user = cur.fetchone()
        conn.close()

        if user and check_password_hash(user[4], request.form["password"]):
            session["user_id"] = user[0]
            session["email"] = user[3]
            session["full_name"] = f"{user[1]} {user[2]}"
            return redirect(url_for("home"))

        flash("Invalid login", "error")

    return render_template("login.html")

@app.route("/home")
def home():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("home.html", name=session["full_name"])

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

# ================= SAVE PIN-POINT LOCATION =================
@app.route("/save_location", methods=["POST"])
def save_location():
    data = request.json
    latest_location["lat"] = data.get("lat")
    latest_location["lon"] = data.get("lon")
    return jsonify({"status": "location saved"})

# ================= PROVIDE LOCATION =================
@app.route("/get_location", methods=["GET"])
def get_location():
    return jsonify(latest_location)

# ================= START LISTENING =================
import os

CONTROL_FLAG = "control.flag"

@app.route("/start_listening", methods=["POST"])
def start_listening_route():
    open(CONTROL_FLAG, "w").close()
    listener_state["running"] = True
    listener_state["emergency"] = False
    return jsonify(listener_state)


@app.route("/stop_listening", methods=["POST"])
def stop_listening_route():
    if os.path.exists(CONTROL_FLAG):
        os.remove(CONTROL_FLAG)
    listener_state["running"] = False
    return jsonify(listener_state)


# ================= EMERGENCY FLAG =================
@app.route("/set_emergency", methods=["POST"])
def set_emergency():

    listener_state["emergency"] = True

    lat = latest_location.get("lat")
    lon = latest_location.get("lon")

    if lat is None or lon is None:
        location_link = "Location unavailable"
    else:
        location_link = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"

    print("🚨 Emergency Location:", location_link)

    # send_sms(location_link)

    return jsonify({"status": "emergency set"})

# ================= LISTENER STATUS =================
@app.route("/listener_status", methods=["GET"])
def listener_status():
    return jsonify(listener_state)

# ================= RUN =================
if __name__ == "__main__":
    app.run(debug=True)
