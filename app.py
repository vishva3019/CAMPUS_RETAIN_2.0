import os
import random
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText

from flask import (
    Flask, render_template, request, redirect,
    session, jsonify, url_for
)
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash

# --------------------------------------------------
# APP CONFIG
# --------------------------------------------------
app = Flask(__name__)
CORS(app)

app.secret_key = os.getenv("SECRET_KEY", "fallback-secret-key")

DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# --------------------------------------------------
# ENV VARIABLES
# --------------------------------------------------
MAIL_USERNAME = os.getenv("MAIL_USERNAME")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

# --------------------------------------------------
# MODELS
# --------------------------------------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)


class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_name = db.Column(db.String(100))
    category = db.Column(db.String(50))
    location = db.Column(db.String(100))
    secret_detail = db.Column(db.Text)
    image_data = db.Column(db.Text)
    status = db.Column(db.String(30), default="Available")
    date_found = db.Column(db.DateTime, default=datetime.utcnow)


class Claim(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("item.id"))
    student_email = db.Column(db.String(120))
    student_id = db.Column(db.String(50))
    phone = db.Column(db.String(20))
    proof_description = db.Column(db.Text)
    status = db.Column(db.String(30), default="Under Review")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class OTPReset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120))
    otp = db.Column(db.String(10))
    expiry = db.Column(db.DateTime)


# --------------------------------------------------
# EMAIL FUNCTION
# --------------------------------------------------
def send_email(receiver, subject, body):
    try:
        if not MAIL_USERNAME or not MAIL_PASSWORD:
            print("Mail credentials missing")
            return False

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = MAIL_USERNAME
        msg["To"] = receiver

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(MAIL_USERNAME, MAIL_PASSWORD)
        server.sendmail(MAIL_USERNAME, receiver, msg.as_string())
        server.quit()

        return True

    except Exception as e:
        print("MAIL ERROR:", e)
        return False


# --------------------------------------------------
# INIT DB
# --------------------------------------------------
@app.route("/init-db")
def init_db():
    db.create_all()
    return "Database initialized successfully!"


# --------------------------------------------------
# LOGIN / REGISTER
# --------------------------------------------------
@app.route("/")
def home():
    return redirect("/login")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].lower().strip()
        password = request.form["password"]

        user = User.query.filter_by(email=email).first()

        # Auto register
        if not user:
            new_user = User(
                email=email,
                password=generate_password_hash(password)
            )
            db.session.add(new_user)
            db.session.commit()

            session["user"] = email
            return redirect("/dashboard")

        # Existing login
        if check_password_hash(user.password, password):
            session["user"] = email
            return redirect("/dashboard")

        return render_template("login.html", error="Wrong password")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# --------------------------------------------------
# FORGOT PASSWORD
# --------------------------------------------------
@app.route("/forgot-password", methods=["POST"])
def forgot_password():
    try:
        email = request.form["email"].lower().strip()

        user = User.query.filter_by(email=email).first()
        if not user:
            return "No account found"

        otp = str(random.randint(100000, 999999))

        old = OTPReset.query.filter_by(email=email).first()
        if old:
            db.session.delete(old)
            db.session.commit()

        row = OTPReset(
            email=email,
            otp=otp,
            expiry=datetime.utcnow() + timedelta(minutes=10)
        )

        db.session.add(row)
        db.session.commit()

        send_email(
            email,
            "Campus Retain OTP",
            f"Your OTP is {otp}"
        )

        return "OTP sent successfully"

    except Exception as e:
        return str(e)


@app.route("/verify-otp", methods=["POST"])
def verify_otp():
    email = request.form["email"].lower().strip()
    otp = request.form["otp"]
    new_password = request.form["password"]

    row = OTPReset.query.filter_by(email=email, otp=otp).first()

    if not row:
        return "Invalid OTP"

    if datetime.utcnow() > row.expiry:
        return "OTP expired"

    user = User.query.filter_by(email=email).first()
    user.password = generate_password_hash(new_password)

    db.session.delete(row)
    db.session.commit()

    return "Password reset successful"


# --------------------------------------------------
# DASHBOARD
# --------------------------------------------------
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/login")

    items = Item.query.order_by(Item.id.desc()).all()
    return render_template(
        "index.html",
        items=items,
        email=session["user"]
    )


# --------------------------------------------------
# REPORT ITEM
# --------------------------------------------------
@app.route("/api/report", methods=["POST"])
def report_item():
    if "user" not in session:
        return "Login required"

    item = Item(
        item_name=request.form["item_name"],
        category=request.form["category"],
        location=request.form["location"],
        secret_detail=request.form["secret_detail"],
        image_data="",
        status="Available"
    )

    db.session.add(item)
    db.session.commit()

    return "Item reported successfully"


# --------------------------------------------------
# CLAIM ITEM
# --------------------------------------------------
@app.route("/api/claim", methods=["POST"])
def claim_item():
    try:
        if "user" not in session:
            return "Login required"

        item_id = request.form["item_id"]

        item = Item.query.get(item_id)

        if not item:
            return "Item not found"

        if item.status == "Claimed":
            return "Already claimed"

        claim = Claim(
            item_id=item_id,
            student_email=session["user"],
            student_id=request.form["student_id"],
            phone=request.form["phone"],
            proof_description=request.form["proof"]
        )

        db.session.add(claim)
        db.session.commit()

        return "Claim submitted successfully"

    except Exception as e:
        return str(e)


# --------------------------------------------------
# ADMIN LOGIN
# --------------------------------------------------
@app.route("/admin_login", methods=["GET", "POST"])
def admin_login():
    try:
        if request.method == "POST":
            email = request.form["email"]
            password = request.form["password"]

            if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
                session["admin"] = True
                return redirect("/admin")

            return render_template(
                "admin_login.html",
                error="Invalid credentials"
            )

        return render_template("admin_login.html")

    except Exception as e:
        return str(e)


# --------------------------------------------------
# ADMIN PANEL
# --------------------------------------------------
@app.route("/admin")
def admin():
    if not session.get("admin"):
        return redirect("/admin_login")

    items = Item.query.all()
    claims = Claim.query.order_by(Claim.id.desc()).all()

    return render_template(
        "admin.html",
        items=items,
        claims=claims
    )


# --------------------------------------------------
# APPROVE CLAIM
# --------------------------------------------------
@app.route("/api/admin/approve/<int:claim_id>", methods=["POST"])
def approve_claim(claim_id):
    if not session.get("admin"):
        return "Unauthorized"

    claim = Claim.query.get(claim_id)
    item = Item.query.get(claim.item_id)

    claim.status = "Approved"
    item.status = "Claimed"

    others = Claim.query.filter(
        Claim.item_id == item.id,
        Claim.id != claim.id
    ).all()

    for c in others:
        c.status = "Rejected"

        send_email(
            c.student_email,
            "Claim Rejected",
            f"Your claim for {item.item_name} was rejected."
        )

    send_email(
        claim.student_email,
        "Claim Approved",
        f"Your claim for {item.item_name} is approved."
    )

    db.session.commit()

    return "Approved"


# --------------------------------------------------
# REJECT CLAIM
# --------------------------------------------------
@app.route("/api/admin/reject/<int:claim_id>", methods=["POST"])
def reject_claim(claim_id):
    if not session.get("admin"):
        return "Unauthorized"

    claim = Claim.query.get(claim_id)
    claim.status = "Rejected"

    send_email(
        claim.student_email,
        "Claim Rejected",
        "Your claim was rejected."
    )

    db.session.commit()

    return "Rejected"


# --------------------------------------------------
# RUN
# --------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)