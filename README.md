# Campus Retain 2.0 🎒
**To Access The Website:** [https://campus-retain-2-0.vercel.app/](https://campus-retain-2-0.vercel.app/)

Campus Retain 2.0 is a premium, high-performance **Lost and Found Management System** tailored for university campuses. Built with an elegant, modern UI featuring ambient mesh gradients and glassmorphism, it allows students and administrators to efficiently report, search, audit, and claim lost belongings.

This platform bridges the communication gap on campus, significantly reducing the turnaround time required to return items to their rightful owners.

---

## 🚀 Features

### 👨‍🎓 Student Portal Features
- **Secure Domain Authentication:** Identity protection strictly matching campus organization emails (`@ced.alliance.edu.in`).
- **Discovery Registry:** Instantly report found items with detailed descriptive metadata, categories, and specific locations.
- **Visual Image Previews:** Upload item photographs encoded instantly into base64 storage strings.
- **Dynamic Inventory Search:** High-performance, character-matching search filter bar to browse available items instantly.
- **Possession Claim Pipeline:** Submit unique identifier attributes (proof description) that only the true owner would know.
- **Forgot Password Recovery:** Secure email-based OTP (One-Time Password) workflow to cleanly reset account credentials if forgotten.

### 👨‍💼 Administration Features
- **Cyber-Dark Operations Terminal:** Premium dark-themed administrative dashboard giving real-time tracking metrics (Total Records, Pending Reviews, Successfully Claimed).
- **Dual Decision Engine:** Distinct interactive operations for pending claims:
  - **Approve Claim:** Marks an asset as securely handed over and locks its public status to `Claimed`.
  - **Reject Claim:** Prompts the admin for custom rationale remarks, instantly alerts the student, and returns the asset to `Available` status for public discovery.
- **Claim History Audit Logs:** A clean chronological feed showing past claim attempts, historical proof inputs, and user coordinates for every item.
- **Resolution Cleanup:** Permanent destructive item deletion capabilities to manage active warehouse inventory.

### 🔔 Integrated Notifications
- **Email Dispatch Pipeline:** Automated secure SMTP notifications triggering on Account Registration, Claim Submissions, Approvals, and Rejections (including admin remarks).
- **Cellular SMS alerts:** Twilio API integration providing immediate SMS alerts straight to the student's phone.

---

## 🛠️ Tech Stack

### Frontend
- **HTML5 & Vanilla JavaScript** (Fetch API integration for server transactions)
- **Tailwind CSS** (Modern utility-first styling layout configurations)
- **Animate.css** (Hardware-accelerated micro-interaction entry effects)

### Backend
- **Python / Flask** (Application layer architecture)

### Database & Storage
- **PostgreSQL / Neon DB Engine** (Production relational database)
- **SQLAlchemy ORM** (Model mapping and relational table routing)
- **Base64 String Encoding** (Embedded asset image persistence mapping)

### Deployment
- **Vercel** (Serverless cloud build optimization)

---

## 📂 Project Structure

```text
Campus-Retain-2.0/
│── app.py                 # Core Flask Backend, API Pipelines, and Database Models
│── requirements.txt       # Production System Dependencies
│── vercel.json            # Vercel Deployment & Route Configuration
│
├── templates/             # Jinja2 Layout Visual Blueprints
│   ├── login.html         # Student Authentication & Forgot Password Interface
│   ├── reset_password.html# Code OTP Password Reset Form
│   ├── admin_login.html   # Cyber-Dark Administrative Gateway
│   ├── index.html         # Main Student Search Feed & Form Modals
│   └── admin.html         # Master Administration Control Panel
│
└── static/                # Static Resource Management Channels
    └── uploads/           # Legacy local storage asset space



⚙️ Installation & Local Setup
1️⃣ Clone the Repository
Bash
git clone [https://github.com/vishva3019/CAMPUS_RETAIN_2.0.git](https://github.com/vishva3019/CAMPUS_RETAIN_2.0.git)
cd CAMPUS_RETAIN_2.0
2️⃣ Establish a Virtual Environment
Bash
python -m venv .venv
source .venv/bin/activate       # Mac/Linux
.venv\Scripts\activate          # Windows
3️⃣ Install Dependencies
Bash
pip install -r requirements.txt
4️⃣ Inject Environment Variables
Create an absolute environment configuration file named .env inside your root project directory:

Ini, TOML
DATABASE_URL=your_postgresql_or_neon_db_url
SECRET_KEY=your_secure_flask_session_secret_key
ADMIN_EMAIL=admin_account@college.edu
ADMIN_PASSWORD=your_secure_admin_password

MAIL_USERNAME=your_gmail_or_smtp_account@gmail.com
MAIL_PASSWORD=your_smtp_app_specific_password

TWILIO_ACCOUNT_SID=your_twilio_sid_token
TWILIO_AUTH_TOKEN=your_twilio_secret_auth_token
TWILIO_PHONE_NUMBER=your_allocated_twilio_phone_number
5️⃣ Boot the Application Locally
Bash
python app.py
Open http://127.0.0.1:5000 in your web browser.

🌐 Deployment on Vercel
Commit and push your code updates to your remote GitHub repository.

Link and import the corresponding repository inside your Vercel Dashboard.

Replicate all configuration parameters declared inside your local .env profile into Vercel's Environment Variables console settings.

Trigger the live Deploy engine.

Database Table Synchronization: On your initial live deployment run, manually navigate to https://your-app-name.vercel.app/init-db in your web browser to automatically build and map your PostgreSQL table schemas.

👨‍💻 Author
VISHVANTH B.Tech Student in Computer Science and Engineering | Full-Stack Developer | Problem Solver - GitHub: https://github.com/vishva3019

📄 License
This repository is reserved strictly for academic evaluations and educational campus implementations.
