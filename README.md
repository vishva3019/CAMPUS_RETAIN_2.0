# Campus Retain 2.0 🎒
**To Access The Website:** [https://campus-retain-2-0.vercel.app/](https://campus-retain-2-0.vercel.app/)

Campus Retain 2.0 is a robust **Lost and Found Management System** tailored for university campuses. It streamlines the lifecycle of lost belongings by giving students an easy reporting interface and giving administrators complete tracking and notification governance.

This platform bridges the communication gap between students and administrative services while optimizing inventory turnover.

---

## 🚀 Features

### 👨‍🎓 Student Features
- **Secure Authentication:** Identity verification strictly enforced through organization emails (`@ced.alliance.edu.in`).
- **Discovery Registration:** Instantly report found items with detailed metadata and location tagging.
- **Visual Uploads:** Snap or upload asset photos natively encoded directly into storage.
- **Claim Ecosystem:** Submit unique possession validation proofs and verification parameters to confirm property ownership.
- **Traceability:** Automatic status adjustments (Available / Review / Claimed) visible site-wide.

### 👨‍💼 Admin Features
- **Centralized Dashboard:** Real-time summary statistics tracking entire inventory quantities, pending evaluations, and resolved handovers.
- **Dynamic Decision Pipeline:** Fully active individual decision buttons for every unique query:
  - **Approve Claim:** Resolves validation ownership and transitions state parameters to `Claimed`.
  - **Reject Claim (New):** Prompt-driven system to pass diagnostic feedback remarks directly to claimants while reverting the status to `Available` for active discovery.
- **Claim History Log (New):** Scrollable chronological audit feeds showing historical attempts, contact contexts, and validation summaries per item profile.
- **Resolution Cleanup:** Permanent destructive item deletion capabilities once administrative claims conclude.

### 🔔 Automated Notifications
- **Email Alerts:** Handled by secure SMTP integrations alerting students during lifecycle transitions (Registration, Approval, and Rejections).
- **SMS Integration:** Embedded Twilio API pipeline dispatching immediate cellular alerts with precise management feedback details.

---

## 🛠️ Tech Stack

### Frontend
- HTML5
- CSS3 (Tailwind CSS framework)
- JavaScript (Fetch API integration)

### Backend
- Python
- Flask framework

### Database & Storage
- PostgreSQL (Neon DB Engine)
- SQLAlchemy ORM wrapper
- Base64 internal string encoding for binary image blobs

### Deployment
- Vercel Serverless Architecture

### External Services
- Twilio REST API
- Secured SMTP Transport Engine

---

## 📂 Project Structure


Campus-Retain-2.0/
│── app.py
│── requirements.txt
│── vercel.json
│
├── templates/
│   ├── login.html
│   ├── admin_login.html
│   ├── index.html
│   └── admin.html
│
└── static/
    └── uploads/


    
⚙️ Installation (Local Setup)

1️⃣ Clone Repository
Bash
git clone [https://github.com/vishva3019/CAMPUS_RETAIN_2.0.git](https://github.com/vishva3019/CAMPUS_RETAIN_2.0.git)
cd CAMPUS_RETAIN_2.0

2️⃣ Establish Virtual Environment
Bash
python -m venv .venv
source .venv/bin/activate       # Mac/Linux
.venv\Scripts\activate          # Windows

3️⃣ Install Dependencies
Bash
pip install -r requirements.txt

4️⃣ Inject Environment Variables
Create a .env file within your root project directory and declare your infrastructure credentials:

Ini, TOML
DATABASE_URL=your_postgresql_url
SECRET_KEY=your_secret_key
ADMIN_EMAIL=admin@college.edu
ADMIN_PASSWORD=your_password

MAIL_USERNAME=your_email@gmail.com
MAIL_PASSWORD=your_app_password

TWILIO_ACCOUNT_SID=your_sid
TWILIO_AUTH_TOKEN=your_token
TWILIO_PHONE_NUMBER=your_number

5️⃣ Run the Application Locally
Bash
python app.py

🌐 Deployment on Vercel
Commit and push code updates to your remote GitHub repository.

Link and import the corresponding repository into your Vercel Dashboard.

Replicate all credentials found inside your .env configuration file straight into Vercel's Environment Variables console settings.

Trigger the live Deploy engine.

🔐 System Administration Login
Access administrative governance tools directly via the management dashboard by applying the specific criteria embedded into your environment settings:

ADMIN_EMAIL: Declared inside your environment profile

ADMIN_PASSWORD: Declared inside your environment profile

📌 Future Improvements
QR code item generation for quick identification.

AI image-matching capabilities to pair lost items with found reports automatically.

Live administrative telemetry analytics.

Cross-platform native mobile build variations.

👨‍💻 Author
VISHVANTH

B.Tech Student | Developer | Problem Solver

GitHub: https://github.com/vishva3019

📄 License
This repository is reserved strictly for academic and educational evaluations.
