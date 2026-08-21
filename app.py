import os
import smtplib
import base64
import json
import random
from typing import Any
from datetime import datetime, timedelta, timezone
from functools import wraps
from email.mime.text import MIMEText

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from sqlalchemy.orm import selectinload, joinedload
from werkzeug.security import generate_password_hash, check_password_hash

from ai.vision import analyze_item_image
from ai.matching import find_potential_matches
from ai.search import semantic_search
from ai.claims import analyze_claim
from ai.assistant import handle_chat_interaction
from ai.config import AIConfig

def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


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

db_url = os.environ.get("DATABASE_URL", "sqlite:///campusretain.db")

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
IS_MAINTENANCE = False


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
    secret_detail = db.Column(db.String(255))
    image_data = db.Column(db.Text)
    status = db.Column(db.String(50), default="Available")
    item_type = db.Column(db.String(20), default="found")
    reported_by = db.Column(db.String(120), nullable=True)
    date_found = db.Column(db.DateTime, default=utcnow)
    date_lost = db.Column(db.DateTime, nullable=True)

    # Phase 3: AI Vision Metadata
    ai_category = db.Column(db.String(50), nullable=True)
    ai_primary_color = db.Column(db.String(30), nullable=True)
    ai_secondary_colors = db.Column(db.JSON, nullable=True)
    ai_brand = db.Column(db.String(50), nullable=True)
    ai_model = db.Column(db.String(50), nullable=True)
    ai_visible_text = db.Column(db.JSON, nullable=True)
    ai_distinctive_features = db.Column(db.JSON, nullable=True)
    ai_condition = db.Column(db.String(30), nullable=True)
    ai_confidence = db.Column(db.Float, nullable=True)
    ai_analysis_status = db.Column(db.String(20), default="not_applicable")
    ai_analyzed_at = db.Column(db.DateTime, nullable=True)

    claims = db.relationship("Claim", backref="item", lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "location": self.location,
            "secret_detail": self.secret_detail,
            "image_data": self.image_data,
            "status": self.status,
            "item_type": self.item_type or "found",
            "reported_by": self.reported_by,
            "date_found": self.date_found.isoformat() if self.date_found else None,
            "date_lost": self.date_lost.isoformat() if self.date_lost else None,
            "ai_category": self.ai_category,
            "ai_primary_color": self.ai_primary_color,
            "ai_secondary_colors": self.ai_secondary_colors,
            "ai_brand": self.ai_brand,
            "ai_model": self.ai_model,
            "ai_visible_text": self.ai_visible_text,
            "ai_distinctive_features": self.ai_distinctive_features,
            "ai_condition": self.ai_condition,
            "ai_confidence": self.ai_confidence,
            "ai_analysis_status": self.ai_analysis_status,
            "ai_analyzed_at": self.ai_analyzed_at.isoformat() if self.ai_analyzed_at else None,
        }


class Claim(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("item.id"), nullable=False)
    student_id = db.Column(db.String(50))
    student_email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    proof_description = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=utcnow)

    # Phase 6: AI-Assisted Claim Verification Metadata
    ai_confidence_score = db.Column(db.Integer, nullable=True)
    ai_confidence_level = db.Column(db.String(20), nullable=True)
    ai_matching_factors = db.Column(db.JSON, nullable=True)
    ai_conflicting_factors = db.Column(db.JSON, nullable=True)
    ai_explanation = db.Column(db.Text, nullable=True)
    ai_recommendation = db.Column(db.String(50), default="manual_review")
    ai_analysis_status = db.Column(db.String(20), default="pending")
    ai_analyzed_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "item_id": self.item_id,
            "student_id": self.student_id,
            "student_email": self.student_email,
            "phone": self.phone,
            "proof_description": self.proof_description,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "ai_confidence_score": self.ai_confidence_score,
            "ai_confidence_level": self.ai_confidence_level,
            "ai_matching_factors": self.ai_matching_factors,
            "ai_conflicting_factors": self.ai_conflicting_factors,
            "ai_explanation": self.ai_explanation,
            "ai_recommendation": self.ai_recommendation or "manual_review",
            "ai_analysis_status": self.ai_analysis_status,
            "ai_analyzed_at": self.ai_analyzed_at.isoformat() if self.ai_analyzed_at else None,
        }


class ItemMatch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lost_item_id = db.Column(db.Integer, db.ForeignKey("item.id"), nullable=False)
    found_item_id = db.Column(db.Integer, db.ForeignKey("item.id"), nullable=False)
    match_score = db.Column(db.Integer, nullable=False)
    confidence = db.Column(db.String(20), nullable=False)
    matching_attributes = db.Column(db.JSON, nullable=True)
    differences = db.Column(db.JSON, nullable=True)
    explanation = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default="active")
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    lost_item = db.relationship("Item", foreign_keys=[lost_item_id], backref="lost_matches")
    found_item = db.relationship("Item", foreign_keys=[found_item_id], backref="found_matches")

    def to_dict(self):
        return {
            "id": self.id,
            "lost_item_id": self.lost_item_id,
            "found_item_id": self.found_item_id,
            "match_score": self.match_score,
            "confidence": self.confidence,
            "matching_attributes": self.matching_attributes or [],
            "differences": self.differences or [],
            "explanation": self.explanation,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ==================================================
# UTILITIES: NOTIFICATIONS
# ==================================================

def send_email(receiver, subject, body):
    if not (MAIL_USERNAME and MAIL_PASSWORD):
        print("Email config missing")
        return False

    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
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
# SAFE SCHEMA SYNCHRONIZATION & MIGRATION
# ==================================================

_schema_initialized = False

def ensure_schema():
    """Idempotently synchronizes the database schema by adding missing columns/tables
    without data loss or table drops. Safe for both PostgreSQL (Neon) and SQLite.
    """
    global _schema_initialized
    try:
        # Step 1: Create any missing tables (e.g. item_match, user, claim, item)
        db.create_all()

        dialect = db.engine.dialect.name
        with db.engine.begin() as conn:
            if dialect == "sqlite":
                item_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(item)")).fetchall()]
                claim_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(claim)")).fetchall()]

                item_additions = [
                    ("item_type", "VARCHAR(20) DEFAULT 'found'"),
                    ("reported_by", "VARCHAR(120)"),
                    ("date_lost", "TIMESTAMP"),
                    ("ai_category", "VARCHAR(50)"),
                    ("ai_primary_color", "VARCHAR(30)"),
                    ("ai_secondary_colors", "JSON"),
                    ("ai_brand", "VARCHAR(50)"),
                    ("ai_model", "VARCHAR(50)"),
                    ("ai_visible_text", "JSON"),
                    ("ai_distinctive_features", "JSON"),
                    ("ai_condition", "VARCHAR(30)"),
                    ("ai_confidence", "FLOAT"),
                    ("ai_analysis_status", "VARCHAR(20) DEFAULT 'not_applicable'"),
                    ("ai_analyzed_at", "TIMESTAMP"),
                ]
                for col_name, col_type in item_additions:
                    if col_name not in item_cols:
                        conn.execute(text(f"ALTER TABLE item ADD COLUMN {col_name} {col_type}"))

                claim_additions = [
                    ("ai_confidence_score", "INTEGER"),
                    ("ai_confidence_level", "VARCHAR(20)"),
                    ("ai_matching_factors", "JSON"),
                    ("ai_conflicting_factors", "JSON"),
                    ("ai_explanation", "TEXT"),
                    ("ai_recommendation", "VARCHAR(50) DEFAULT 'manual_review'"),
                    ("ai_analysis_status", "VARCHAR(20) DEFAULT 'pending'"),
                    ("ai_analyzed_at", "TIMESTAMP"),
                ]
                for col_name, col_type in claim_additions:
                    if col_name not in claim_cols:
                        conn.execute(text(f"ALTER TABLE claim ADD COLUMN {col_name} {col_type}"))

                conn.execute(text("UPDATE item SET item_type = 'found' WHERE item_type IS NULL"))

            elif dialect == "postgresql":
                postgres_sql = """
                ALTER TABLE item ADD COLUMN IF NOT EXISTS item_type VARCHAR(20) DEFAULT 'found';
                ALTER TABLE item ADD COLUMN IF NOT EXISTS reported_by VARCHAR(120);
                ALTER TABLE item ADD COLUMN IF NOT EXISTS date_lost TIMESTAMP;
                ALTER TABLE item ADD COLUMN IF NOT EXISTS ai_category VARCHAR(50);
                ALTER TABLE item ADD COLUMN IF NOT EXISTS ai_primary_color VARCHAR(30);
                ALTER TABLE item ADD COLUMN IF NOT EXISTS ai_secondary_colors JSON;
                ALTER TABLE item ADD COLUMN IF NOT EXISTS ai_brand VARCHAR(50);
                ALTER TABLE item ADD COLUMN IF NOT EXISTS ai_model VARCHAR(50);
                ALTER TABLE item ADD COLUMN IF NOT EXISTS ai_visible_text JSON;
                ALTER TABLE item ADD COLUMN IF NOT EXISTS ai_distinctive_features JSON;
                ALTER TABLE item ADD COLUMN IF NOT EXISTS ai_condition VARCHAR(30);
                ALTER TABLE item ADD COLUMN IF NOT EXISTS ai_confidence FLOAT;
                ALTER TABLE item ADD COLUMN IF NOT EXISTS ai_analysis_status VARCHAR(20) DEFAULT 'not_applicable';
                ALTER TABLE item ADD COLUMN IF NOT EXISTS ai_analyzed_at TIMESTAMP;

                UPDATE item SET item_type = 'found' WHERE item_type IS NULL;

                ALTER TABLE claim ADD COLUMN IF NOT EXISTS ai_confidence_score INTEGER;
                ALTER TABLE claim ADD COLUMN IF NOT EXISTS ai_confidence_level VARCHAR(20);
                ALTER TABLE claim ADD COLUMN IF NOT EXISTS ai_matching_factors JSON;
                ALTER TABLE claim ADD COLUMN IF NOT EXISTS ai_conflicting_factors JSON;
                ALTER TABLE claim ADD COLUMN IF NOT EXISTS ai_explanation TEXT;
                ALTER TABLE claim ADD COLUMN IF NOT EXISTS ai_recommendation VARCHAR(50) DEFAULT 'manual_review';
                ALTER TABLE claim ADD COLUMN IF NOT EXISTS ai_analysis_status VARCHAR(20) DEFAULT 'pending';
                ALTER TABLE claim ADD COLUMN IF NOT EXISTS ai_analyzed_at TIMESTAMP;
                """
                for statement in postgres_sql.strip().split(";"):
                    stmt = statement.strip()
                    if stmt:
                        conn.execute(text(stmt))

        _schema_initialized = True
        return True
    except Exception as e:
        app.logger.warning(f"Schema synchronization warning: {e}")
        return False


# ==================================================
# AUTH DECORATORS & TRAFFIC INTERCEPTORS
# ==================================================

@app.before_request
def check_for_maintenance():
    bypass_routes = [
        "static", "login", "admin_login", "admin_dashboard", "logout",
        "reject_claim", "approve_claim", "delete_item", "test_email",
        "forgot_password", "reset_password"
    ]
    
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
            if request.path.startswith("/api/") or request.is_json:
                return jsonify({
                    "status": "error",
                    "error": "Authentication required. Please sign in.",
                    "message": "Authentication required.",
                    "success": False
                }), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            if request.path.startswith("/api/") or request.is_json:
                return jsonify({"error": "Administrator authorization required.", "success": False}), 403
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return wrapper


# ==================================================
# ROUTES
# ==================================================

@app.route("/")
def index():
    user_email = session.get("user_email")

    # Found items in the public inventory
    items = Item.query.filter(
        (Item.item_type == "found") | (Item.item_type == None)
    ).order_by(Item.date_found.desc()).all()

    # User's reported lost items
    my_lost_items = (
        Item.query.filter_by(item_type="lost", reported_by=user_email)
        .order_by(Item.date_found.desc())
        .all()
        if user_email
        else []
    )

    # Fetch active match counts in single grouped queries instead of N+1 individual queries
    found_match_counts = dict(
        db.session.query(ItemMatch.found_item_id, db.func.count(ItemMatch.id))
        .filter(ItemMatch.status == "active")
        .group_by(ItemMatch.found_item_id)
        .all()
    )
    lost_match_counts = dict(
        db.session.query(ItemMatch.lost_item_id, db.func.count(ItemMatch.id))
        .filter(ItemMatch.status == "active")
        .group_by(ItemMatch.lost_item_id)
        .all()
    )

    for item in items:
        item.match_count = found_match_counts.get(item.id, 0)

    for item in my_lost_items:
        item.match_count = lost_match_counts.get(item.id, 0)

    return render_template(
        "index.html",
        items=items,
        my_lost_items=my_lost_items,
        user_email=user_email,
    )


@app.route("/dashboard")
@login_required
def dashboard():
    user_email = session.get("user_email")
    items = Item.query.filter(
        (Item.item_type == "found") | (Item.item_type == None)
    ).order_by(Item.date_found.desc()).all()

    my_lost_items = (
        Item.query.filter_by(item_type="lost", reported_by=user_email)
        .order_by(Item.date_found.desc())
        .all()
        if user_email
        else []
    )

    found_match_counts = dict(
        db.session.query(ItemMatch.found_item_id, db.func.count(ItemMatch.id))
        .filter(ItemMatch.status == "active")
        .group_by(ItemMatch.found_item_id)
        .all()
    )
    lost_match_counts = dict(
        db.session.query(ItemMatch.lost_item_id, db.func.count(ItemMatch.id))
        .filter(ItemMatch.status == "active")
        .group_by(ItemMatch.lost_item_id)
        .all()
    )

    for item in items:
        item.match_count = found_match_counts.get(item.id, 0)

    for item in my_lost_items:
        item.match_count = lost_match_counts.get(item.id, 0)

    return render_template(
        "dashboard.html",
        items=items,
        my_lost_items=my_lost_items,
        user_email=user_email,
    )


# ---------------- USER AUTHENTICATION ----------------

@app.route("/login", methods=["GET", "POST"])
def login():
    try:
        if "user_email" in session:
            return redirect(url_for("index"))

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
        session["reset_expiry"] = (utcnow() + timedelta(minutes=10)).isoformat()
        
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
        if utcnow() > expiry_time:
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
    items = (
        Item.query.options(selectinload(Item.claims))
        .order_by(Item.date_found.desc())
        .all()
    )
    matches = (
        ItemMatch.query.options(
            joinedload(ItemMatch.lost_item),
            joinedload(ItemMatch.found_item),
        )
        .filter_by(status="active")
        .order_by(ItemMatch.match_score.desc())
        .all()
    )
    return render_template("admin.html", items=items, matches=matches)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))





# ---------- AI MULTIMODAL IMAGE ANALYSIS ENDPOINT ----------

@app.route("/api/ai/analyze-image", methods=["POST"])
@login_required
def api_ai_analyze_image():
    try:
        user_email = session.get("user_email", "anonymous")
        image_bytes = None
        mime_type = "image/jpeg"

        if request.files and "image" in request.files:
            f = request.files["image"]
            if f and f.filename:
                image_bytes = f.read()
                mime_type = f.content_type or "image/jpeg"

        if not image_bytes and request.is_json:
            raw_img = request.json.get("image")
            if raw_img:
                if raw_img.startswith("data:"):
                    header, data = raw_img.split(",", 1)
                    if "image/" in header:
                        mime_type = header.split(";")[0].replace("data:", "")
                    image_bytes = base64.b64decode(data)
                else:
                    image_bytes = base64.b64decode(raw_img)

        if not image_bytes and request.form.get("image"):
            raw_img = request.form.get("image")
            if raw_img:
                if raw_img.startswith("data:"):
                    header, data = raw_img.split(",", 1)
                    if "image/" in header:
                        mime_type = header.split(";")[0].replace("data:", "")
                    image_bytes = base64.b64decode(data)
                else:
                    image_bytes = base64.b64decode(raw_img)

        if not image_bytes:
            return jsonify({
                "success": False,
                "error": "No image file provided in upload request.",
                "data": None
            }), 400

        app.logger.info(
            f"AI image analysis requested by {user_email}: provider={AIConfig.get_provider()}, "
            f"model={AIConfig.get_model()}, configured={AIConfig.is_configured()}, "
            f"timeout={AIConfig.get_timeout()}s, mime={mime_type}, size={len(image_bytes)} bytes"
        )
        res = analyze_item_image(image_bytes)

        if res.get("success") and res.get("data"):
            d = res["data"]
            app.logger.info(f"AI image analysis completed for {user_email}: category={d.get('category')}, brand={d.get('brand')}, color={d.get('primary_color')}")
        else:
            app.logger.warning(f"AI image analysis failed for {user_email}: {res.get('error')}")

        return jsonify(res)

    except Exception as e:
        app.logger.exception("AI image analysis endpoint error")
        return jsonify({
            "success": False,
            "error": "AI vision analysis is temporarily unavailable. Please try again.",
            "data": None
        }), 200


# ---------- AI MATCHING HELPER & ENDPOINTS ----------

def sync_item_matches(target_item: Item) -> list[dict]:
    try:
        target_dict = target_item.to_dict()
        opposing_type = "lost" if (target_item.item_type or "found") == "found" else "found"

        candidates = Item.query.filter(
            Item.item_type == opposing_type,
            Item.id != target_item.id,
            Item.status != "Claimed"
        ).all()

        if not candidates:
            return []

        candidate_dicts = [c.to_dict() for c in candidates]
        match_response = find_potential_matches(target_dict, candidate_dicts)
        match_results = (
            match_response.get("data", {}).get("matches", [])
            if isinstance(match_response, dict)
            else match_response
        )

        saved_matches = []
        for m in match_results:
            cand_id = m.get("candidate_id") or m.get("matched_item_id")
            if not cand_id:
                continue

            lost_id = target_item.id if target_item.item_type == "lost" else cand_id
            found_id = cand_id if target_item.item_type == "lost" else target_item.id

            existing = ItemMatch.query.filter_by(
                lost_item_id=lost_id,
                found_item_id=found_id
            ).first()

            if existing:
                existing.match_score = m["match_score"]
                existing.confidence = m["confidence"]
                existing.matching_attributes = m.get("matching_attributes", [])
                existing.differences = m.get("differences", [])
                existing.explanation = m.get("explanation")
                existing.status = "active"
                existing.updated_at = utcnow()
            else:
                match_record = ItemMatch(
                    lost_item_id=lost_id,
                    found_item_id=found_id,
                    match_score=m["match_score"],
                    confidence=m["confidence"],
                    matching_attributes=m.get("matching_attributes", []),
                    differences=m.get("differences", []),
                    explanation=m.get("explanation"),
                    status="active",
                    created_at=utcnow(),
                )
                db.session.add(match_record)

            m_formatted = {
                "matched_item_id": cand_id,
                "matched_item_name": m.get("candidate_name") or m.get("matched_item_name"),
                "matched_item_category": m.get("candidate_category") or m.get("matched_item_category"),
                "matched_item_location": m.get("candidate_location") or m.get("matched_item_location"),
                "matched_item_image": m.get("candidate_image") or m.get("matched_item_image"),
                "matched_item_type": opposing_type,
                "matched_item_status": m.get("candidate_status", "Available"),
                "match_score": m["match_score"],
                "confidence": m["confidence"],
                "matching_attributes": m.get("matching_attributes", []),
                "differences": m.get("differences", []),
                "explanation": m.get("explanation"),
            }
            saved_matches.append(m_formatted)

        db.session.commit()
        return saved_matches
    except Exception as e:
        app.logger.exception(f"Error syncing item matches for item {target_item.id}: {e}")
        return []


# ---------- REPORT DISCOVERY PIPELINE ----------

@app.route("/api/report", methods=["POST"])
@login_required
def report_item():
    try:
        f = request.files.get("image")
        image_b64 = None
        raw_bytes = None

        if f and f.filename:
            raw_bytes = f.read()
            image_b64 = (
                "data:" + (f.content_type or "image/jpeg") +
                ";base64," +
                base64.b64encode(raw_bytes).decode()
            )

        ai_data = None
        raw_ai_meta = request.form.get("ai_metadata")
        if raw_ai_meta:
            try:
                ai_data = json.loads(raw_ai_meta)
            except Exception:
                ai_data = None

        ai_status = "not_applicable"
        if ai_data:
            ai_status = "completed"
        elif raw_bytes:
            try:
                ai_res = analyze_item_image(raw_bytes)
                if ai_res.get("success") and ai_res.get("data"):
                    ai_data = ai_res["data"]
                    ai_status = "completed"
                else:
                    ai_status = "failed"
            except Exception:
                ai_status = "failed"

        item = Item(
            name=request.form["name"],
            category=request.form.get("category", "Other"),
            location=request.form["location"],
            secret_detail=request.form.get("secret_detail", ""),
            image_data=image_b64,
            item_type="found",
            status="Available",
            reported_by=session.get("user_email"),
            ai_category=ai_data.get("category") if ai_data else None,
            ai_primary_color=ai_data.get("primary_color") if ai_data else None,
            ai_secondary_colors=ai_data.get("secondary_colors") if ai_data else None,
            ai_brand=ai_data.get("brand") if ai_data else None,
            ai_model=ai_data.get("model") if ai_data else None,
            ai_visible_text=ai_data.get("visible_text") if ai_data else None,
            ai_distinctive_features=ai_data.get("distinctive_features") if ai_data else None,
            ai_condition=ai_data.get("condition") if ai_data else None,
            ai_confidence=ai_data.get("confidence") if ai_data else None,
            ai_analysis_status=ai_status,
            ai_analyzed_at=utcnow() if ai_data else None
        )

        db.session.add(item)
        db.session.commit()

        # Trigger background match syncing against active lost item reports
        matches = sync_item_matches(item)

        if ADMIN_EMAIL:
            send_email(
                ADMIN_EMAIL,
                "New Item Reported",
                f"A new discovered asset entry '{item.name}' has been logged into the registry."
            )

        return jsonify({
            "status": "success",
            "item_id": item.id,
            "ai_status": ai_status,
            "match_count": len(matches)
        })

    except Exception as e:
        app.logger.exception("Error during item reporting")
        return jsonify({"error": "Failed to log item into inventory."}), 500


# ---------- REPORT LOST ITEM PIPELINE ----------

@app.route("/api/report-lost", methods=["POST"])
@login_required
def report_lost_item():
    """Submit a lost item report and discover instant potential matches."""
    try:
        f = request.files.get("image")
        image_b64 = None
        raw_bytes = None

        if f and f.filename:
            raw_bytes = f.read()
            image_b64 = (
                "data:" + (f.content_type or "image/jpeg") +
                ";base64," +
                base64.b64encode(raw_bytes).decode()
            )

        ai_data = None
        raw_ai_meta = request.form.get("ai_metadata")
        if raw_ai_meta:
            try:
                ai_data = json.loads(raw_ai_meta)
            except Exception:
                ai_data = None

        ai_status = "not_applicable"
        if ai_data:
            ai_status = "completed"
        elif raw_bytes:
            try:
                ai_res = analyze_item_image(raw_bytes)
                if ai_res.get("success") and ai_res.get("data"):
                    ai_data = ai_res["data"]
                    ai_status = "completed"
                else:
                    ai_status = "failed"
            except Exception:
                ai_status = "failed"

        item = Item(
            name=request.form["name"],
            category=request.form.get("category", "Other"),
            location=request.form["location"],
            secret_detail=request.form.get("secret_detail", ""),
            image_data=image_b64,
            item_type="lost",
            status="Active",
            reported_by=session.get("user_email"),
            ai_category=ai_data.get("category") if ai_data else None,
            ai_primary_color=ai_data.get("primary_color") if ai_data else None,
            ai_secondary_colors=ai_data.get("secondary_colors") if ai_data else None,
            ai_brand=ai_data.get("brand") if ai_data else None,
            ai_model=ai_data.get("model") if ai_data else None,
            ai_visible_text=ai_data.get("visible_text") if ai_data else None,
            ai_distinctive_features=ai_data.get("distinctive_features") if ai_data else None,
            ai_condition=ai_data.get("condition") if ai_data else None,
            ai_confidence=ai_data.get("confidence") if ai_data else None,
            ai_analysis_status=ai_status,
            ai_analyzed_at=utcnow() if ai_data else None
        )

        db.session.add(item)
        db.session.commit()

        # Trigger automatic matching against found items
        matches = sync_item_matches(item)

        return jsonify({
            "status": "success",
            "item_id": item.id,
            "match_count": len(matches),
            "matches": matches
        })

    except Exception as e:
        app.logger.exception("Error reporting lost item")
        return jsonify({"error": "Failed to register lost item report."}), 500


# ---------- RETRIEVE MATCHES FOR AN ITEM ----------

@app.route("/api/ai/matches/<int:item_id>", methods=["GET"])
def api_get_item_matches(item_id):
    try:
        item = db.session.get(Item, item_id)
        if not item:
            return jsonify({"success": False, "error": "Item not found"}), 404

        matches = sync_item_matches(item)

        return jsonify({
            "success": True,
            "data": {
                "item_id": item.id,
                "item_name": item.name,
                "item_type": item.item_type or "found",
                "matches": matches
            },
            "error": None
        })
    except Exception as e:
        app.logger.exception(f"Error fetching matches for item {item_id}")
        return jsonify({
            "success": False,
            "error": "Failed to fetch AI match discovery.",
            "data": None
        }), 200


# ---------- AI NATURAL LANGUAGE SEARCH ENDPOINT ----------

@app.route("/api/ai/search", methods=["POST"])
def api_ai_search():
    """Natural Language semantic search endpoint."""
    try:
        data = request.json or {}
        query = data.get("query", "").strip()

        if not query:
            return jsonify({
                "success": False,
                "error": "Search query cannot be empty.",
                "data": None
            }), 400

        # Retrieve candidate items from database
        try:
            db_items = Item.query.filter(
                (Item.status != "Claimed") | (Item.status == None)
            ).all()
            item_dicts = [it.to_dict() for it in db_items]
        except Exception as db_err:
            app.logger.warning(f"Database query error in AI search: {db_err}")
            item_dicts = []

        # Execute semantic search pipeline
        res = semantic_search(query, item_dicts, top_n=20)
        return jsonify(res)

    except Exception as e:
        app.logger.exception("AI search endpoint error")
        return jsonify({
            "success": False,
            "error": "Search service is temporarily unavailable.",
            "data": None
        }), 200


# ---------- AI CONVERSATIONAL ASSISTANT ENDPOINT ----------

@app.route("/api/ai/chat", methods=["POST"])
def api_ai_chat():
    """Conversational AI Assistant endpoint for students and visitors."""
    try:
        message = ""
        history = []
        if request.is_json and request.json:
            message = request.json.get("message", "").strip()
            history = request.json.get("history", [])
        elif request.form:
            message = request.form.get("message", "").strip()

        # Retrieve available inventory items from database for grounding
        try:
            db_items = Item.query.filter(
                (Item.status != "Claimed") | (Item.status == None)
            ).all()
            item_dicts = [it.to_dict() for it in db_items]
        except Exception as db_err:
            app.logger.warning(f"Database query error in AI chat: {db_err}")
            item_dicts = []

        res = handle_chat_interaction(message, item_dicts, history=history)
        return jsonify(res)

    except Exception as e:
        app.logger.exception("AI assistant endpoint error")
        return jsonify({
            "success": True,
            "data": {
                "message": "Campus Retain AI is temporarily unavailable. You can still use the normal search and lost/found reporting features.",
                "intent": "error",
                "results": [],
                "suggested_actions": ["🔎 Search inventory", "📝 Report lost item"]
            },
            "error": None
        }), 200


# ---------- AI CLAIM VERIFICATION HELPER & ENDPOINTS ----------

def analyze_and_persist_claim_ai(claim: Claim, item: Item) -> dict[str, Any] | None:
    try:
        claim_dict = claim.to_dict()
        item_dict = item.to_dict()

        res = analyze_claim(claim_dict, item_dict)
        if res.get("success") and res.get("data"):
            d = res["data"]
            claim.ai_confidence_score = d.get("confidence_score")
            claim.ai_confidence_level = d.get("confidence_level")
            claim.ai_matching_factors = d.get("matching_factors")
            claim.ai_conflicting_factors = d.get("conflicting_factors")
            claim.ai_explanation = d.get("explanation")
            claim.ai_recommendation = d.get("recommendation", "manual_review")
            claim.ai_analysis_status = d.get("analysis_status", "completed")
            claim.ai_analyzed_at = utcnow()
            db.session.commit()
            return d
        else:
            claim.ai_analysis_status = "failed"
            db.session.commit()
            return None
    except Exception as e:
        app.logger.exception(f"Error persisting AI claim analysis for claim {claim.id}: {e}")
        claim.ai_analysis_status = "failed"
        db.session.commit()
        return None


@app.route("/api/ai/claim-assessment/<int:claim_id>", methods=["GET"])
@login_required
def api_get_claim_assessment(claim_id):
    try:
        claim = db.session.get(Claim, claim_id)
        if not claim:
            return jsonify({"success": False, "error": "Claim record not found"}), 404

        item = db.session.get(Item, claim.item_id)
        if not item:
            return jsonify({"success": False, "error": "Associated item not found"}), 404

        if claim.ai_confidence_score is None:
            analyze_and_persist_claim_ai(claim, item)

        return jsonify({
            "success": True,
            "data": {
                "claim_id": claim.id,
                "item_id": item.id,
                "item_name": item.name,
                "student_id": claim.student_id,
                "confidence_score": claim.ai_confidence_score,
                "confidence_level": claim.ai_confidence_level,
                "matching_factors": claim.ai_matching_factors or [],
                "conflicting_factors": claim.ai_conflicting_factors or [],
                "explanation": claim.ai_explanation,
                "recommendation": claim.ai_recommendation or "manual_review",
                "analysis_status": claim.ai_analysis_status,
                "analyzed_at": claim.ai_analyzed_at.isoformat() if claim.ai_analyzed_at else None
            },
            "error": None
        })

    except Exception as e:
        app.logger.exception(f"Error retrieving claim assessment for claim {claim_id}")
        return jsonify({
            "success": False,
            "error": "Failed to retrieve claim assessment.",
            "data": None
        }), 200


@app.route("/api/ai/analyze-claim/<int:claim_id>", methods=["POST"])
@login_required
def api_analyze_claim_endpoint(claim_id):
    try:
        claim = db.session.get(Claim, claim_id)
        if not claim:
            return jsonify({"success": False, "error": "Claim not found"}), 404

        item = db.session.get(Item, claim.item_id)
        if not item:
            return jsonify({"success": False, "error": "Item not found"}), 404

        data = analyze_and_persist_claim_ai(claim, item)
        if data:
            return jsonify({"success": True, "data": data, "error": None})
        else:
            return jsonify({
                "success": False,
                "error": "AI claim analysis could not be completed.",
                "data": None
            }), 200

    except Exception as e:
        app.logger.exception(f"Error re-analyzing claim {claim_id}")
        return jsonify({
            "success": False,
            "error": "Failed to re-analyze claim.",
            "data": None
        }), 200


# ---------- CLAIM REGISTRATION PIPELINE ----------

@app.route("/api/claim", methods=["POST"])
@login_required
def claim_item():
    try:
        data = request.get_json(silent=True) or {}
        item_id = data.get("item_id")
        student_id = (data.get("student_id") or "").strip()
        phone = (data.get("phone") or "").strip()
        proof_description = (data.get("proof_description") or "").strip()

        # User is authenticated via @login_required; use ONLY authenticated session email
        student_email = session.get("user_email")
        if not student_email:
            return jsonify({
                "status": "error",
                "message": "Authentication required."
            }), 401

        if not item_id:
            return jsonify({
                "status": "error",
                "message": "Item identifier is required."
            }), 400

        if not student_id or not proof_description:
            return jsonify({
                "status": "error",
                "message": "Student ID and ownership proof description are required."
            }), 400

        item = db.session.get(Item, item_id)
        if not item:
            return jsonify({
                "status": "error",
                "message": "The requested item was not found."
            }), 404

        if item.status == "Claimed":
            return jsonify({
                "status": "error",
                "message": "This item has already been claimed."
            }), 400

        item.status = "Pending"

        claim = Claim(
            item_id=item.id,
            student_id=student_id,
            student_email=student_email,
            phone=phone,
            proof_description=proof_description,
            ai_analysis_status="pending"
        )

        db.session.add(claim)
        db.session.commit()

        # Run AI claim verification assistance immediately (does not fail claim creation)
        try:
            analyze_and_persist_claim_ai(claim, item)
        except Exception as ai_exc:
            app.logger.warning(f"AI claim verification encountered error for claim {claim.id}: {ai_exc}")

        # Notification delivery is secondary; failure must not prevent successful claim creation
        email_sent = False
        sms_sent = False

        try:
            email_sent = bool(send_email(
                student_email,
                "Campus Retain Claim Submitted",
                f"Your claim request for '{item.name}' is submitted and under review."
            ))
            if ADMIN_EMAIL:
                admin_body = (
                    f"Hello Admin,\n\n"
                    f"A new claim request has been submitted for item: '{item.name}'.\n\n"
                    f"Student ID: {student_id}\n"
                    f"Student Email: {student_email}\n"
                    f"Phone: {phone}\n"
                    f"Proof Description: {proof_description}\n\n"
                    f"Please review this inside your Admin Management dashboard."
                )
                send_email(ADMIN_EMAIL, "Alert: New Claim Submitted", admin_body)
        except Exception as mail_exc:
            app.logger.warning(f"Email dispatch error for claim {claim.id}: {mail_exc}")

        try:
            if phone:
                sms_sent = bool(send_sms(
                    phone,
                    f"Campus Retain: Claim request for {item.name} submitted."
                ))
        except Exception as sms_exc:
            app.logger.warning(f"SMS dispatch error for claim {claim.id}: {sms_exc}")

        return jsonify({
            "status": "success",
            "message": "Claim submitted successfully. Your request is now under review.",
            "claim_id": claim.id,
            "email_sent": email_sent,
            "sms_sent": sms_sent
        }), 200

    except Exception as e:
        app.logger.exception("Unexpected error in /api/claim")
        return jsonify({
            "status": "error",
            "message": "Unable to submit the claim. Please try again."
        }), 500


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
            return jsonify({"status": "error", "error": "Item not found."}), 404

        # Safely remove all dependent AI match records referencing this item (lost or found)
        ItemMatch.query.filter(
            (ItemMatch.lost_item_id == item_id) | (ItemMatch.found_item_id == item_id)
        ).delete(synchronize_session=False)

        # Safely remove all dependent Claim records referencing this item
        Claim.query.filter_by(item_id=item_id).delete(synchronize_session=False)

        # Remove the item
        db.session.delete(item)
        db.session.commit()

        app.logger.info(f"Item #{item_id} successfully deleted by admin {session.get('admin_email') or session.get('user_email')}")
        return jsonify({"status": "success", "message": f"Item #{item_id} deleted successfully."})

    except Exception as e:
        db.session.rollback()
        app.logger.error(
            f"Item deletion failed: item_id={item_id}, error_type={type(e).__name__}, reason={str(e)}"
        )
        return jsonify({"status": "error", "error": "Unable to delete this item. Please try again."}), 500


# ==================================================
# DIAGNOSTICS & INFRASTRUCTURE SANITY CHECKS
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
