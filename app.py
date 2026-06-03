import os
import smtplib
import base64
import random
from datetime import datetime, timedelta
from functools import wraps
from email.mime.text import MIMEText

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

# Optional Twilio
try:
    from twilio.rest import Client
except:
    Client = None

app = Flask(__name__)

# ==================================================
# CONFIG & CORE VARIABLES
# ==================================================

app.secret_key = os.environ.get("SECRET_KEY", "fallback-secret-key")

db_url = os.environ.get("DATABASE_URL")

if not db_url:
    raise Exception("DATABASE_URL is not set.")

if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = "static/uploads"
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

# Email Infrastructure Config
MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")

# Twilio Infrastructure Config
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER")

# Admin Infrastructure Config
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")

db = SQLAlchemy(app)

# ==================================================
# GLOBAL MAINTENANCE TOGGLE
# ==================================================
# Change this flag to True to instantly lock public user paths and render
# the clean 3-dot loading maintenance page during codebase upgrades.
IS_MAINTENANCE = True


# ==================================================
# MODELS
# ==================================================

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)


class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(50))
    location = db.Column(db.String(150))
    secret_detail = db.Column(db.Text)
    image_data = db.Column(db.Text)
    status = db.Column(db.String(30), default="Available")
    date_found = db.Column(db.DateTime, default=datetime.utcnow)

    claims = db.relationship(
        "Claim",
        backref="item",
        lazy=True,
        cascade="all, delete-orphan"
    )


class Claim(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("item.id"), nullable=False)
    student_id = db.Column(db.String(50))
    student_email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    proof_description = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


# ==================================================
# HELPERS
# ==================================================

def send_email(receiver, subject, body):
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        print("Email config missing")
        return False

    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        
        # FIXED: Explicit Display Name configuration added to clear enterprise gateway spam filters
        msg["From"] = f"CampusRetain Portal <{MAIL_USERNAME}>"
        msg["To"] = receiver

        with smtplib.SMTP(MAIL_SERVER, MAIL_PORT) as server:
            server.starttls()
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
            server.send_message(msg)

        print("Email sent successfully")
        return True

    except Exception as e:
        print("Email Error:", str(e))
        return False


def send_sms(receiver, body):
    if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_PHONE_NUMBER and Client):
        print("Twilio config missing")
        return False

    try:
        number = ''.join(filter(str.isdigit, receiver))

        if len(number) == 10:
            receiver = f"+91{number}"
        elif not receiver.startswith("+"):
            receiver = f"+{number}"

        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

        client.messages.create(
            body=body,
            from_=TWILIO_PHONE_NUMBER,
            to=receiver
        )

        print("SMS sent successfully")
        return True

    except Exception as e:
        print("SMS Error:", str(e))
        return False


# ==================================================
# AUTH DECORATORS & TRAFFIC INTERCEPTORS
# ==================================================

@app.before_request
def check_for_maintenance():
    bypass_routes = ["static", "admin_login", "admin_dashboard", "logout", "init_db", "reject_claim", "approve_claim", "delete_item", "test_email"]
    
    if IS_MAINTENANCE:
        if request.endpoint and any(route in request.endpoint for route in bypass_routes):
            return None
            
        if session.get("is_admin") == True:
            return None
            
        return render_template("maintenance.html"), 503


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_email" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("is_admin") != True:
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return wrapper


# ==================================================
# ROUTES
# ==================================================

@app.route("/")
@login_required
def index():
    items = Item.query.order_by(Item.date_found.desc()).all()
    return render_template(
        "index.html",
        items=items,
        user_email=session.get("user_email")
    )


# ---------------- USER AUTHENTICATION ----------------

@app.route("/login", methods=["GET", "POST"])
def login():
    try:
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")

            if not email.endswith("@ced.alliance.edu.in"):
                return render_template(
                    "login.html",
                    error="Only organization emails allowed."
                )

            user = User.query.filter_by(email=email).first()

            if not user:
                new_user = User(
                    email=email,
                    password=generate_password_hash(password)
                )
                db.session.add(new_user)
                db.session.commit()

                session["user_email"] = email

                send_email(
                    email,
                    "Campus Retain Registration Successful",
                    "Welcome to Campus Retain. Your account has been created successfully."
                )

                return redirect(url_for("index"))

            try:
                valid = check_password_hash(user.password, password)
            except:
                valid = (user.password == password)

            if valid:
                session["user_email"] = email
                return redirect(url_for("index"))

            return render_template(
                "login.html",
                error="Incorrect password. Click 'Forgot Password?' to reset it."
            )

        return render_template("login.html")

    except Exception as e:
        return f"Login Error: {str(e)}"


# ---------------- FORGOT PASSWORD (OTP GENERATION) ----------------

@app.route("/forgot-password", methods=["POST"])
def forgot_password():
    try:
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email).first()
        
        if not user:
            return render_template("login.html", error="This email address is not registered in the network inventory.")
            
        otp = str(random.randint(100000, 999999))
        
        session["reset_email"] = email
        session["reset_otp"] = otp
        session["reset_expiry"] = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
        
        email_body = f"Hello,\n\nYou requested a password reset for Campus Retain.\nYour 6-digit verification code OTP is: {otp}\n\nThis code is valid for 10 minutes. If you did not initialize this configuration, please secure your credentials immediately."
        send_email(email, "Campus Retain - Password Reset Verification OTP", email_body)
        
        return render_template("reset_password.html", email=email, message="Verification code has been systematically delivered to your organization inbox.")
        
    except Exception as e:
        return render_template("login.html", error=f"Reset Initialization Fault: {str(e)}")


# ---------------- RESET PASSWORD (OTP VERIFICATION) ----------------

@app.route("/reset-password", methods=["POST"])
def reset_password():
    try:
        email = session.get("reset_email")
        session_otp = session.get("reset_otp")
        expiry_str = session.get("reset_expiry")
        
        input_otp = request.form.get("otp", "").strip()
        new_password = request.form.get("new_password", "")
        
        if not email or not session_otp or not expiry_str:
            return render_template("login.html", error="Recovery session expired. Please initialize password recovery sequence again.")
            
        expiry_time = datetime.fromisoformat(expiry_str)
        if datetime.utcnow() > expiry_time:
            return render_template("login.html", error="Verification code token expired. Please try again.")
            
        if input_otp != session_otp:
            return render_template("reset_password.html", email=email, error="Invalid verification code parameters. Please recheck.")
            
        user = User.query.filter_by(email=email).first()
        if user:
            user.password = generate_password_hash(new_password)
            db.session.commit()
            
            session.pop("reset_email", None)
            session.pop("reset_otp", None)
            session.pop("reset_expiry", None)
            
            return render_template("login.html", success="Security password restructured cleanly! Proceed to access portal.")
            
        return render_template("login.html", error="System database user lookup constraint error.")
        
    except Exception as e:
        return render_template("login.html", error=f"Password Restructuring Error: {str(e)}")


# ---------------- ADMIN ACCESS AND MANAGEMENT ----------------

@app.route("/admin_login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
            session["is_admin"] = True
            session["user_email"] = email
            return redirect(url_for("admin_dashboard"))

        return render_template(
            "admin_login.html",
            error="Invalid administrative terminal credentials."
        )

    return render_template("admin_login.html")


@app.route("/admin")
@admin_required
def admin_dashboard():
    items = Item.query.order_by(Item.date_found.desc()).all()
    return render_template("admin.html", items=items)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------- DB SCHEMAS INITIALIZATION ----------------

@app.route("/init-db")
def init_db():
    try:
        db.create_all()
        return "Database architecture schemas initialized successfully!"
    except Exception as e:
        return f"Database Schema Construction Fault Error: {str(e)}"


# ==================================================
# API CONTROLLERS ENDPOINTS
# ==================================================

# ---------- REPORT DISCOVERY PIPELINE ----------

@app.route("/api/report", methods=["POST"])
@login_required
def report_item():
    try:
        f = request.files.get("image")
        image_b64 = None

        if f and f.filename:
            image_b64 = (
                "data:" + f.content_type +
                ";base64," +
                base64.b64encode(f.read()).decode()
            )

        item = Item(
            name=request.form["name"],
            category=request.form.get("category", "Other"),
            location=request.form["location"],
            secret_detail=request.form.get("secret_detail", ""),
            image_data=image_b64
        )

        db.session.add(item)
        db.session.commit()

        if ADMIN_EMAIL:
            send_email(
                ADMIN_EMAIL,
                "New Item Reported",
                f"A new discovered asset entry '{item.name}' has been logged into the registry."
            )

        return jsonify({"status": "success"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- ALLOCATE CLAIM QUERY ----------

@app.route("/api/claim", methods=["POST"])
@login_required
def claim_item():
    try:
        data = request.json

        item = db.session.get(Item, data["item_id"])
        if not item:
            return jsonify({"error": "Target item not found inside current channel"}), 404

        item.status = "Pending"

        claim = Claim(
            item_id=data["item_id"],
            student_id=data["student_id"],
            student_email=data["student_email"],
            phone=data.get("phone", ""),
            proof_description=data["proof_description"]
        )

        db.session.add(claim)
        db.session.commit()

        # 1. Notify Student Lifecycle
        send_email(
            data["student_email"],
            "Campus Retain Claim Submitted",
            f"Your claim request for '{item.name}' is submitted and under review."
        )

        # 2. FIXED: Administrative copy alert now triggers properly inside your primary workspace
        if ADMIN_EMAIL:
            admin_body = f"Hello Admin,\n\nA new claim request has been submitted for item: '{item.name}'.\n\nStudent ID: {data['student_id']}\nProof Description: {data['proof_description']}\n\nPlease review this inside your Admin Management dashboard."
            send_email(ADMIN_EMAIL, "Alert: New Claim Submitted", admin_body)

        send_sms(
            data.get("phone", ""),
            f"Campus Retain: Claim request for {item.name} submitted."
        )

        return jsonify({"status": "success"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- EXECUTE APPROVAL TERMINAL ----------

@app.route("/api/admin/approve/<int:item_id>", methods=["POST"])
@admin_required
def approve_claim(item_id):
    try:
        item = db.session.get(Item, item_id)
        if not item:
            return jsonify({"error": "Target entity not found"}), 404

        item.status = "Claimed"

        latest_claim = Claim.query.filter_by(
            item_id=item_id
        ).order_by(
            Claim.timestamp.desc()
        ).first()

        db.session.commit()

        if latest_claim:
            send_email(
                latest_claim.student_email,
                "Campus Retain Claim Approved 🎉",
                f"Congratulations! Your ownership verification profile parameters for '{item.name}' matched our requirements. Please physically retrieve the item asset at the DOSS office."
            )

            send_sms(
                latest_claim.phone,
                f"Campus Retain Notice: Claim approved for asset {item.name}. Visit DOSS office for claim."
            )

        return jsonify({"status": "success"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- EXECUTE REJECTION FLOW AND REMARKS ----------

@app.route("/api/admin/reject/<int:item_id>", methods=["POST"])
@admin_required
def reject_claim(item_id):
    try:
        data = request.json or {}
        remarks = data.get("remarks", "").strip()
        if not remarks:
            remarks = "Verification details provided did not match item specifications."
        
        item = db.session.get(Item, item_id)
        if not item:
            return jsonify({"error": "Target system item coordinates missing"}), 404

        item.status = "Available"

        latest_claim = Claim.query.filter_by(
            item_id=item_id
        ).order_by(
            Claim.timestamp.desc()
        ).first()

        db.session.commit()

        if latest_claim:
            send_email(
                latest_claim.student_email,
                "Campus Verification Update - Claim Rejected",
                f"Your claim request query for item entry '{item.name}' was evaluated and rejected.\n\nFeedback/Remarks from Admin: {remarks}\n\nIf you have further questions, visit the DOSS office for more."
            )

            send_sms(
                latest_claim.phone,
                f"Campus Retain: Claim rejected for asset {item.name}. Remarks feedback parameter: {remarks}"
            )

        return jsonify({"status": "success"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- EXPUNGE ITEM RECORD ----------

@app.route("/api/item/delete/<int:item_id>", methods=["POST"])
@admin_required
def delete_item(item_id):
    try:
        item = db.session.get(Item, item_id)
        if not item:
            return jsonify({"error": "Target object not tracked inside database data models"}), 404

        db.session.delete(item)
        db.session.commit()

        return jsonify({"status": "success"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==================================================
# INFRASTRUCTURE DEPLOYMENT SANITY CHECKS
# ==================================================

@app.route("/test-email")
def test_email():
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        return "Configuration Error: MAIL_USERNAME or MAIL_PASSWORD is completely empty in your Vercel Dashboard!"

    try:
        msg = MIMEText("Testing SMTP transport layer connections from CampusRetain.")
        msg["Subject"] = "Campus Retain Diagnostic Check"
        msg["From"] = f"CampusRetain Portal <{MAIL_USERNAME}>"
        msg["To"] = ADMIN_EMAIL if ADMIN_EMAIL else "vishvanth3049@gmail.com"

        server = smtplib.SMTP(MAIL_SERVER, MAIL_PORT)
        server.starttls()
        server.login(MAIL_USERNAME, MAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        return "Success! Connection authorized and test email sent smoothly to your administrator address."
    except Exception as e:
        return f"SMTP Connection Failed! The exact error message from Google is: <br><br><strong>{str(e)}</strong>"


@app.route("/test-sms")
def test_sms():
    send_sms(
        "+919686193049",
        "Campus Retain Twilio notification systems channel validation check successful."
    )
    return "Test Cellular Text Transmitted Successfully"


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
