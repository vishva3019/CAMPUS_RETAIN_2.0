import os
import random
from datetime import datetime, timedelta

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, jsonify
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash


# =====================================================
# APP CONFIG
# =====================================================
app = Flask(__name__)

app.secret_key = os.getenv("SECRET_KEY", "fallback-secret-key")

# IMPORTANT: DB config BEFORE SQLAlchemy(app)
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL",
    "sqlite:///campusretain.db"
)

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# =====================================================
# MODELS
# =====================================================

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)


class LostItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_name = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(100))
    location = db.Column(db.String(200))
    description = db.Column(db.Text)
    status = db.Column(db.String(50), default="Available")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ClaimRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("lost_item.id"))
    claimer_email = db.Column(db.String(150))
    message = db.Column(db.Text)
    status = db.Column(db.String(50), default="Under Review")


# =====================================================
# INIT DB
# =====================================================
with app.app_context():
    db.create_all()


# =====================================================
# HOME
# =====================================================
@app.route("/")
def home():
    items = LostItem.query.order_by(LostItem.created_at.desc()).all()
    return render_template("index.html", items=items)


# =====================================================
# LOGIN PAGE
# =====================================================
@app.route("/login")
def login():
    return render_template("login.html")


# =====================================================
# LOGIN / AUTO REGISTER
# =====================================================
@app.route("/login_submit", methods=["POST"])
def login_submit():
    email = request.form["email"].strip().lower()
    password = request.form["password"]

    user = User.query.filter_by(email=email).first()

    # Auto Register
    if not user:
        hashed = generate_password_hash(password)
        user = User(email=email, password=hashed)
        db.session.add(user)
        db.session.commit()

    # Existing user login
    if check_password_hash(user.password, password):
        session["user"] = email
        return redirect(url_for("home"))

    flash("Wrong password. Use Forgot Password.")
    return redirect(url_for("login"))


# =====================================================
# LOGOUT
# =====================================================
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# =====================================================
# REPORT ITEM
# =====================================================
@app.route("/api/report", methods=["POST"])
def report_item():
    if "user" not in session:
        return jsonify({"success": False, "message": "Login required"})

    data = request.json

    item = LostItem(
        item_name=data.get("item_name"),
        category=data.get("category"),
        location=data.get("location"),
        description=data.get("description"),
        status="Available"
    )

    db.session.add(item)
    db.session.commit()

    return jsonify({"success": True})


# =====================================================
# CLAIM ITEM
# =====================================================
@app.route("/api/claim", methods=["POST"])
def claim_item():
    if "user" not in session:
        return jsonify({"success": False, "message": "Login required"})

    data = request.json

    claim = ClaimRequest(
        item_id=data.get("item_id"),
        claimer_email=session["user"],
        message=data.get("message"),
        status="Under Review"
    )

    db.session.add(claim)
    db.session.commit()

    return jsonify({"success": True})


# =====================================================
# ADMIN LOGIN PAGE
# =====================================================
@app.route("/admin_login")
def admin_login():
    return render_template("admin_login.html")


# =====================================================
# ADMIN LOGIN
# =====================================================
@app.route("/admin_login_submit", methods=["POST"])
def admin_login_submit():
    email = request.form["email"]
    password = request.form["password"]

    admin_email = os.getenv("ADMIN_EMAIL", "admin@campus.com")
    admin_password = os.getenv("ADMIN_PASSWORD", "admin123")

    if email == admin_email and password == admin_password:
        session["admin"] = True
        return redirect(url_for("admin"))

    flash("Invalid Admin Login")
    return redirect(url_for("admin_login"))


# =====================================================
# ADMIN DASHBOARD
# =====================================================
@app.route("/admin")
def admin():
    if "admin" not in session:
        return redirect(url_for("admin_login"))

    claims = ClaimRequest.query.order_by(ClaimRequest.id.desc()).all()
    return render_template("admin.html", claims=claims)


# =====================================================
# APPROVE CLAIM
# =====================================================
@app.route("/api/admin/approve/<int:claim_id>", methods=["POST"])
def approve_claim(claim_id):
    if "admin" not in session:
        return jsonify({"success": False})

    claim = ClaimRequest.query.get(claim_id)

    if not claim:
        return jsonify({"success": False})

    claim.status = "Approved"

    # Reject others
    other_claims = ClaimRequest.query.filter(
        ClaimRequest.item_id == claim.item_id,
        ClaimRequest.id != claim.id
    ).all()

    for c in other_claims:
        c.status = "Rejected"

    # Item marked claimed
    item = LostItem.query.get(claim.item_id)
    if item:
        item.status = "Claimed"

    db.session.commit()

    return jsonify({"success": True})


# =====================================================
# REJECT CLAIM
# =====================================================
@app.route("/api/admin/reject/<int:claim_id>", methods=["POST"])
def reject_claim(claim_id):
    if "admin" not in session:
        return jsonify({"success": False})

    claim = ClaimRequest.query.get(claim_id)

    if claim:
        claim.status = "Rejected"
        db.session.commit()

    return jsonify({"success": True})


# =====================================================
# FORGOT PASSWORD (TEMP)
# =====================================================
@app.route("/forgot_password", methods=["POST"])
def forgot_password():
    email = request.form["email"].strip().lower()
    new_password = request.form["new_password"]

    user = User.query.filter_by(email=email).first()

    if user:
        user.password = generate_password_hash(new_password)
        db.session.commit()
        flash("Password Reset Successful")
    else:
        flash("Email not found")

    return redirect(url_for("login"))


# =====================================================
# RUN
# =====================================================
if __name__ == "__main__":
    app.run(debug=True)