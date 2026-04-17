import os
import smtplib
from functools import wraps
import base64
from datetime import datetime
from email.mime.text import MIMEText
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

# OPTIONAL: Twilio (safe import)
try:
    from twilio.rest import Client
except:
    Client = None

app = Flask(__name__)

# --- SECRET KEY ---
app.secret_key = os.environ.get('SECRET_KEY', 'fallback-secret-key')

# --- DATABASE CONFIG ---
db_url = os.environ.get('DATABASE_URL')

if not db_url:
    raise Exception("DATABASE_URL is not set. Please configure it in Vercel.")

# Fix postgres:// issue
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- FILE CONFIG ---
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# --- EMAIL CONFIG (SAFE) ---
MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')

# --- TWILIO CONFIG ---
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER')

db = SQLAlchemy(app)

# --- MODELS ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50))
    location = db.Column(db.String(100))
    secret_detail = db.Column(db.Text)
    image_data = db.Column(db.Text)
    status = db.Column(db.String(20), default='Available')
    date_found = db.Column(db.DateTime, default=datetime.utcnow)
    claims = db.relationship('Claim', backref='item', lazy=True, cascade="all, delete-orphan")

class Claim(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'), nullable=False)
    student_id = db.Column(db.String(50))
    student_email = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    proof_description = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# --- EMAIL FUNCTION ---
def send_email(receiver, subject, body):
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        print("Email not configured")
        return False

    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = MAIL_USERNAME
        msg['To'] = receiver

        with smtplib.SMTP(MAIL_SERVER, MAIL_PORT) as server:
            server.starttls()
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
            server.send_message(msg)

        return True
    except Exception as e:
        print(f"Mail Error: {e}")
        return False

# --- SMS FUNCTION ---
def send_sms(receiver, body):
    if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_PHONE_NUMBER and Client):
        print("Twilio not configured")
        return False

    try:
        clean_num = ''.join(filter(str.isdigit, receiver))
        if len(clean_num) == 10:
            receiver = f"+91{clean_num}"
        elif not receiver.startswith('+'):
            receiver = f"+{clean_num}"

        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        client.messages.create(body=body, from_=TWILIO_PHONE_NUMBER, to=receiver)

        return True
    except Exception as e:
        print(f"SMS Error: {e}")
        return False

# --- DECORATORS ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_email' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('is_admin') != True:
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# --- AUTH ROUTES ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    try:
        if request.method == 'POST':
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')

            if not email.endswith('@ced.alliance.edu.in'):
                return render_template('login.html', error="Only organization emails allowed.")

            user = User.query.filter_by(email=email).first()

            # First time user -> auto register
            if not user:
                hashed_password = generate_password_hash(password)
                new_user = User(email=email, password=hashed_password)
                db.session.add(new_user)
                db.session.commit()

                session['user_email'] = email
                return redirect(url_for('index'))

            # Existing user login
            try:
                valid = check_password_hash(user.password, password)
            except:
                # fallback if old plain text password exists
                valid = (user.password == password)

            if valid:
                session['user_email'] = email
                return redirect(url_for('index'))

            return render_template('login.html', error="Incorrect password.")

        return render_template('login.html')

    except Exception as e:
        return f"Login Error: {str(e)}"

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    admin_email = os.environ.get('ADMIN_EMAIL')
    admin_password = os.environ.get('ADMIN_PASSWORD')

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if email == admin_email and password == admin_password:
            session['is_admin'] = True
            session['user_email'] = email
            return redirect(url_for('admin_dashboard'))

        return render_template('admin_login.html', error="Invalid credentials.")

    return render_template('admin_login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- TEMP DATABASE INIT ROUTE ---
@app.route('/init-db')
def init_db():
    try:
        db.create_all()
        return "✅ Database initialized successfully!"
    except Exception as e:
        return f"❌ Error: {str(e)}"

# --- MAIN ROUTES ---
@app.route('/')
@login_required
def index():
    items = Item.query.order_by(Item.date_found.desc()).all()
    return render_template('index.html', items=items, user_email=session.get('user_email'))

@app.route('/admin')
@admin_required
def admin_dashboard():
    items = Item.query.order_by(Item.date_found.desc()).all()
    return render_template('admin.html', items=items)

# --- API ROUTES ---
@app.route('/api/report', methods=['POST'])
@login_required
def report_item():
    try:
        f = request.files.get('image')
        image_b64 = None

        if f:
            image_b64 = "data:" + f.content_type + ";base64," + base64.b64encode(f.read()).decode()

        new_item = Item(
            name=request.form['name'],
            category=request.form.get('category', 'Other'),
            location=request.form['location'],
            secret_detail=request.form.get('secret_detail', ''),
            image_data=image_b64
        )

        db.session.add(new_item)
        db.session.commit()
        return jsonify({"status": "success"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/claim', methods=['POST'])
@login_required
def claim_item():
    try:
        data = request.json
        item = db.session.get(Item, data['item_id'])

        if item:
            item.status = 'Pending'

        new_claim = Claim(
            item_id=data['item_id'],
            student_id=data['student_id'],
            student_email=data['student_email'],
            phone=data.get('phone', ''),
            proof_description=data['proof_description']
        )

        db.session.add(new_claim)
        db.session.commit()

        return jsonify({"status": "success"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/approve/<int:item_id>', methods=['POST'])
@admin_required
def approve_claim(item_id):
    item = db.session.get(Item, item_id)

    if not item:
        return jsonify({"error": "Not found"}), 404

    item.status = 'Claimed'
    db.session.commit()

    return jsonify({"status": "success"})

@app.route('/api/item/delete/<int:item_id>', methods=['POST'])
@admin_required
def delete_item(item_id):
    item = db.session.get(Item, item_id)

    if not item:
        return jsonify({"error": "Not found"}), 404

    db.session.delete(item)
    db.session.commit()

    return jsonify({"status": "success"})

# --- LOCAL RUN ONLY ---
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)