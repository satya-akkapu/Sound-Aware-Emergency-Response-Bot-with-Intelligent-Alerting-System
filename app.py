from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import random
import secrets
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = "your_secret_key_here"
DB_PATH = "users.db"
#EMAIL CONFIG
EMAIL_ADDRESS = "safetybot2026@gmail.com"
EMAIL_PASSWORD = "qdmk mgwj zylt hvel"
#LOCATION STORAGE
latest_location = {
    "lat": None,
    "lon": None
}
#LISTENER STATE
listener_state = {
    "running": False,
    "emergency": False
}
#DATABASE
def init_db():
    conn = None
    try:
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
                created_at TEXT,
                reset_token TEXT,
                token_expiry TEXT,
                otp TEXT,
                otp_expiry TEXT
            )
        """)
        # Safely add otp/otp_expiry columns if they don't exist
        for col, coltype in [("otp", "TEXT"), ("otp_expiry", "TEXT")]:
            try:
                cur.execute(f"ALTER TABLE users ADD COLUMN {col} {coltype}")
            except sqlite3.OperationalError:
                pass  # Column already exists — skip
        conn.commit()
    finally:
        if conn:
            conn.close()
init_db()
#EMAIL HELPER
def send_otp_email(to_email, otp):
    """Send OTP to the given email address. Returns True on success, False on failure."""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Your Safety Bot Password Reset OTP"
        msg["From"]    = EMAIL_ADDRESS
        msg["To"]      = to_email
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; color: #333;">
            <h2 style="color: #d9534f;">Safety Bot — Password Reset</h2>
            <p>We received a request to reset your password.</p>
            <p>Your One-Time Password (OTP) is:</p>
            <h1 style="letter-spacing: 8px; color: #d9534f;">{otp}</h1>
            <p>This OTP is valid for <strong>5 minutes</strong>.</p>
            <p>If you did not request a password reset, please ignore this email.</p>
            <hr/>
            <small style="color: #888;">Safety Bot Security Team</small>
        </body>
        </html>
        """
        msg.attach(MIMEText(html_body, "html"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.sendmail(EMAIL_ADDRESS, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"[EMAIL ERROR] Failed to send OTP to {to_email}: {e}")
        return False
#ROUTES
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
        conn = None
        try:
            conn = sqlite3.connect(DB_PATH)
            cur  = conn.cursor()
            cur.execute("""
                INSERT INTO users VALUES (NULL,?,?,?,?,?,?,?,NULL,NULL,NULL,NULL)
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
            flash("Registration successful! Please login.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Email already exists", "error")
        finally:
            if conn:
                conn.close()  # Always closes, even on error
    return render_template("register.html")
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = None
        conn = None
        try:
            conn = sqlite3.connect(DB_PATH)
            cur  = conn.cursor()
            cur.execute("SELECT * FROM users WHERE email=?", (request.form["email"],))
            user = cur.fetchone()
        finally:
            if conn:
                conn.close()  # Always closes, even on error
        if user and check_password_hash(user[4], request.form["password"]):
            session["user_id"]   = user[0]
            session["email"]     = user[3]
            session["full_name"] = f"{user[1]} {user[2]}"
            return redirect(url_for("home"))
        flash("Invalid email or password", "error")
    return render_template("login.html")
#FORGOT PASSWORD
@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        user = None
        conn = None
        try:
            conn = sqlite3.connect(DB_PATH)
            cur  = conn.cursor()
            cur.execute("SELECT * FROM users WHERE email=?", (email,))
            user = cur.fetchone()
            if user:
                otp    = str(random.randint(100000, 999999))
                expiry = (datetime.now() + timedelta(minutes=5)).isoformat()

                cur.execute("""
                    UPDATE users SET otp=?, otp_expiry=? WHERE email=?
                """, (otp, expiry, email))
                conn.commit()
        finally:
            if conn:
                conn.close()  # Always closes, even on error
        if user:
            if send_otp_email(email, otp):
                flash("OTP sent to your email! Check your inbox (and spam folder).", "success")
            else:
                flash("Failed to send email. Please check server email configuration.", "error")
            session["reset_email"] = email
            return redirect(url_for("verify_otp"))
        flash("No account found with that email address.", "error")
        return redirect(url_for("forgot_password"))
    return render_template("forgot_password.html")
#VERIFY OTP
@app.route("/verify_otp", methods=["GET", "POST"])
def verify_otp():
    if request.method == "POST":
        email        = request.form.get("email", "").strip().lower()
        entered_otp  = request.form.get("otp", "").strip()
        new_password = request.form.get("password", "")
        user = None
        conn = None
        try:
            conn = sqlite3.connect(DB_PATH)
            cur  = conn.cursor()
            cur.execute("SELECT * FROM users WHERE email=?", (email,))
            user = cur.fetchone()
            if not user:
                flash("User not found!", "error")
                return redirect(url_for("verify_otp"))
            db_otp = user[10]   # otp column
            expiry = user[11]   # otp_expiry column
            if not db_otp:
                flash("No OTP requested. Please request a new one.", "error")
                return redirect(url_for("forgot_password"))
            if datetime.now() > datetime.fromisoformat(expiry):
                flash("OTP has expired. Please request a new one.", "error")
                return redirect(url_for("forgot_password"))
            if entered_otp != db_otp:
                flash("Invalid OTP. Please try again.", "error")
                return redirect(url_for("verify_otp"))
            # OTP is correct — update password and clear OTP fields
            hashed_password = generate_password_hash(new_password)
            cur.execute("""
                UPDATE users SET password_hash=?, otp=NULL, otp_expiry=NULL WHERE email=?
            """, (hashed_password, email))
            conn.commit()
        finally:
            if conn:
                conn.close()  # Always closes, even on error
        session.pop("reset_email", None)
        flash("Password reset successful! Please login.", "success")
        return redirect(url_for("login"))
    # Pre-fill email from session if available
    email = session.get("reset_email", "")
    return render_template("verify_otp.html", email=email)
#RESET PASSWORD (token-based, legacy route)
@app.route("/reset_password/<token>", methods=["GET", "POST"])
def reset_password(token):
    user = None
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cur  = conn.cursor()
        cur.execute("SELECT * FROM users WHERE reset_token=?", (token,))
        user = cur.fetchone()
        if not user:
            flash("Invalid or expired reset link.", "error")
            return redirect(url_for("forgot_password"))
        expiry_time = datetime.fromisoformat(user[9])
        if datetime.now() > expiry_time:
            flash("Reset link has expired. Please request a new one.", "error")
            return redirect(url_for("forgot_password"))
        if request.method == "POST":
            new_password = request.form["password"]
            hashed = generate_password_hash(new_password)
            cur.execute("""
                UPDATE users SET password_hash=?, reset_token=NULL, token_expiry=NULL
                WHERE reset_token=?
            """, (hashed, token))
            conn.commit()
            flash("Password reset successful! Please login.", "success")
            return redirect(url_for("login"))
    finally:
        if conn:
            conn.close()  # Always closes, even on error
    return render_template("reset_password.html")
#HOME
@app.route("/home")
def home():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("home.html", name=session["full_name"])
#LOGOUT
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))
#SAVE PIN-POINT LOCATION
@app.route("/save_location", methods=["POST"])
def save_location():
    data = request.json
    latest_location["lat"] = data.get("lat")
    latest_location["lon"] = data.get("lon")
    return jsonify({"status": "location saved"})
#PROVIDE LOCATION
@app.route("/get_location", methods=["GET"])
def get_location():
    return jsonify(latest_location)
#START LISTENING
CONTROL_FLAG = "control.flag"
@app.route("/start_listening", methods=["POST"])
def start_listening_route():
    open(CONTROL_FLAG, "w").close()
    listener_state["running"]   = True
    listener_state["emergency"] = False
    return jsonify(listener_state)
@app.route("/stop_listening", methods=["POST"])
def stop_listening_route():
    if os.path.exists(CONTROL_FLAG):
        os.remove(CONTROL_FLAG)
    listener_state["running"] = False
    return jsonify(listener_state)
#EMERGENCY FLAG
@app.route("/set_emergency", methods=["POST"])
def set_emergency():
    listener_state["emergency"] = True
    lat = latest_location.get("lat")
    lon = latest_location.get("lon")
    if lat is None or lon is None:
        location_link = "Location unavailable"
    else:
        location_link = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
    print("Emergency Location:", location_link)
    # send_sms(location_link)
    return jsonify({"status": "emergency set"})
#LISTENER STATUS
@app.route("/listener_status", methods=["GET"])
def listener_status():
    return jsonify(listener_state)
#RUN
if __name__ == "__main__":
    app.run(debug=True)