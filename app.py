
import os
import random
import smtplib
import base64
from datetime import datetime, timedelta
from functools import wraps
from email.mime.text import MIMEText

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

try:
    from twilio.rest import Client
except:
    Client = None

app = Flask(__name__)

# ==================================================
# CONFIG
# ==================================================

app.secret_key = os.environ.get("SECRET_KEY", "fallback-secret-key")

db_url = os.environ.get("DATABASE_URL")

if not db_url:
    raise Exception("DATABASE_URL not found")

if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER")

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")

db = SQLAlchemy(app)

# ==================================================
# MODELS
# ==================================================

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)


class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    category = db.Column(db.String(50))
    location = db.Column(db.String(100))
    secret_detail = db.Column(db.Text)
    image_data = db.Column(db.Text)
    status = db.Column(db.String(20), default="Available")
    date_found = db.Column(db.DateTime, default=datetime.utcnow)


class Claim(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("item.id"))
    student_id = db.Column(db.String(50))
    student_email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    proof_description = db.Column(db.Text)
    status = db.Column(db.String(20), default="Submitted")
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


class OTPReset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120))
    otp = db.Column(db.String(10))
    expiry = db.Column(db.DateTime)

# ==================================================
# HELPERS
# ==================================================

def send_email(receiver, subject, body):
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = MAIL_USERNAME
        msg["To"] = receiver

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
            server.send_message(msg)

        return True
    except Exception as e:
        print("Email Error:", e)
        return False


def send_sms(receiver, body):
    try:
        if not Client:
            return False

        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

        client.messages.create(
            body=body,
            from_=TWILIO_PHONE_NUMBER,
            to=receiver
        )
        return True
    except Exception as e:
        print("SMS Error:", e)
        return False


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_email" not in session:
            return redirect("/login")
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("is_admin") != True:
            return redirect("/admin_login")
        return f(*args, **kwargs)
    return wrapper

# ==================================================
# ROUTES
# ==================================================

@app.route("/")
@login_required
def home():
    items = Item.query.order_by(Item.id.desc()).all()
    return render_template("index.html", items=items)

# ==================================================
# LOGIN
# ==================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].lower().strip()
        password = request.form["password"]

        if not email.endswith("@ced.alliance.edu.in"):
            return render_template("login.html", error="Use organization email")

        user = User.query.filter_by(email=email).first()

        # AUTO REGISTER
        if not user:
            new_user = User(
                email=email,
                password=generate_password_hash(password)
            )
            db.session.add(new_user)
            db.session.commit()

            send_email(
                email,
                "Campus Retain Account Created",
                "Your account was automatically created."
            )

            session["user_email"] = email
            return redirect("/")

        # EXISTING USER LOGIN
        if check_password_hash(user.password, password):
            session["user_email"] = email
            return redirect("/")

        return render_template(
            "login.html",
            error="Wrong password. Use Forgot Password."
        )

    return render_template("login.html")

# ==================================================
# FORGOT PASSWORD
# ==================================================

@app.route("/forgot-password", methods=["POST"])
def forgot_password():
    try:
        email = request.form.get("email", "").lower().strip()

        if not email:
            return "Email is required"

        user = User.query.filter_by(email=email).first()

        if not user:
            return "No account found"

        otp = str(random.randint(100000, 999999))

        # Delete old OTP if exists
        old = OTPReset.query.filter_by(email=email).first()
        if old:
            db.session.delete(old)
            db.session.commit()

        # Save new OTP
        row = OTPReset(
            email=email,
            otp=otp,
            expiry=datetime.utcnow() + timedelta(minutes=10)
        )

        db.session.add(row)
        db.session.commit()

        # Send mail
        mail_sent = send_email(
            email,
            "Campus Retain Password Reset OTP",
            f"Your OTP is {otp}\nValid for 10 minutes."
        )

        if not mail_sent:
            return "OTP created but email sending failed"

        return "OTP sent successfully"

    except Exception as e:
        print("FORGOT PASSWORD ERROR:", str(e))
        return f"Server Error: {str(e)}"


@app.route("/reset-password", methods=["POST"])
def reset_password():
    email = request.form["email"].lower()
    otp = request.form["otp"]
    new_password = request.form["new_password"]

    row = OTPReset.query.filter_by(email=email, otp=otp).first()

    if not row:
        return "Invalid OTP"

    if datetime.utcnow() > row.expiry:
        return "OTP Expired"

    user = User.query.filter_by(email=email).first()
    user.password = generate_password_hash(new_password)

    db.session.delete(row)
    db.session.commit()

    return "Password updated"

# ==================================================
# ADMIN
# ==================================================

@app.route("/admin_login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect("/admin")

    return render_template("admin_login.html")


@app.route("/admin")
@admin_required
def admin():
    items = Item.query.all()
    claims = Claim.query.order_by(Claim.timestamp.desc()).all()
    return render_template("admin.html", items=items, claims=claims)

# ==================================================
# REPORT ITEM
# ==================================================

@app.route("/api/report", methods=["POST"])
@login_required
def report():
    f = request.files.get("image")
    image_b64 = None

    if f:
        image_b64 = (
            "data:" + f.content_type +
            ";base64," +
            base64.b64encode(f.read()).decode()
        )

    item = Item(
        name=request.form["name"],
        category=request.form["category"],
        location=request.form["location"],
        secret_detail=request.form["secret_detail"],
        image_data=image_b64
    )

    db.session.add(item)
    db.session.commit()

    return jsonify({"status": "success"})

# ==================================================
# CLAIM ITEM
# ==================================================

@app.route("/api/claim", methods=["POST"])
@login_required
def claim():
    data = request.json

    item = db.session.get(Item, data["item_id"])

    if item.status == "Claimed":
        return jsonify({"error": "Already claimed"}), 400

    claim = Claim(
        item_id=data["item_id"],
        student_id=data["student_id"],
        student_email=data["student_email"],
        phone=data["phone"],
        proof_description=data["proof_description"]
    )

    db.session.add(claim)
    db.session.commit()

    send_email(
        data["student_email"],
        "Claim Submitted",
        f"Your claim for {item.name} is under review."
    )

    return jsonify({"status": "success"})

# ==================================================
# ADMIN APPROVE CLAIM
# ==================================================

@app.route("/api/admin/approve-claim/<int:claim_id>", methods=["POST"])
@admin_required
def approve_claim(claim_id):
    claim = db.session.get(Claim, claim_id)

    if not claim:
        return jsonify({"error": "Not found"}), 404

    item = db.session.get(Item, claim.item_id)

    # Approve selected
    claim.status = "Approved"
    item.status = "Claimed"

    # Reject others
    others = Claim.query.filter(
        Claim.item_id == item.id,
        Claim.id != claim.id
    ).all()

    for other in others:
        other.status = "Rejected"

        send_email(
            other.student_email,
            "Claim Rejected",
            f"Your claim for {item.name} was not approved."
        )

    # Notify approved user
    send_email(
        claim.student_email,
        "Claim Approved",
        f"Your claim for {item.name} has been approved."
    )

    send_sms(
        claim.phone,
        f"Campus Retain: Claim approved for {item.name}"
    )

    db.session.commit()

    return jsonify({"status": "success"})

# ==================================================
# LOGOUT
# ==================================================

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ==================================================
# INIT DB
# ==================================================

@app.route("/init-db")
def initdb():
    db.create_all()
    return "Database initialized"

# ==================================================

if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    app.run(debug=True)