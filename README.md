# Campus Retain 2.0 🎒
To Access The Website : https://campus-retain-2-0.vercel.app/

Campus Retain 2.0 is a **Lost and Found Management System** developed for college campuses to help students and administrators efficiently report, search, claim, and manage lost items.

This platform improves communication between students and admin staff while reducing the time taken to return lost belongings.

---

## 🚀 Features

### 👨‍🎓 Student Features
- Student login using organization email
- Report lost/found items
- Upload item images
- Search available items
- Claim items
- Track claim status

### 👨‍💼 Admin Features
- Secure admin login
- View all reported items
- Approve / reject claims
- Delete resolved items
- Manage lost & found inventory

### 🔔 Notifications
- Email alerts
- SMS integration using Twilio

---

## 🛠️ Tech Stack

### Frontend
- HTML5
- CSS3
- JavaScript

### Backend
- Python
- Flask

### Database
- PostgreSQL (Neon DB)

### Deployment
- Vercel

### Additional Services
- Twilio API
- SMTP Email Service

---

## 📂 Project Structure

```text
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
├── static/
│   └── uploads/

⚙️ Installation (Local Setup)
1️⃣ Clone Repository
git clone https://github.com/vishva3019/CAMPUS_RETAIN_2.0.git
cd CAMPUS_RETAIN_2.0
2️⃣ Create Virtual Environment
python -m venv .venv
source .venv/bin/activate      # Mac/Linux
.venv\Scripts\activate         # Windows
3️⃣ Install Dependencies
pip install -r requirements.txt
4️⃣ Set Environment Variables

Create .env

DATABASE_URL=your_postgresql_url
SECRET_KEY=your_secret_key
ADMIN_EMAIL=admin@college.edu
ADMIN_PASSWORD=your_password

MAIL_USERNAME=your_email@gmail.com
MAIL_PASSWORD=your_app_password

TWILIO_ACCOUNT_SID=your_sid
TWILIO_AUTH_TOKEN=your_token
TWILIO_PHONE_NUMBER=your_number
5️⃣ Run Project
python app.py
🌐 Deployment on Vercel
Push project to GitHub
Import repository into Vercel
Add environment variables
Deploy
🔐 Admin Login

Use credentials stored in environment variables:

ADMIN_EMAIL=
ADMIN_PASSWORD=
📌 Future Improvements
QR code item claiming
AI image-based matching
Real-time notifications
Student dashboard analytics
Mobile app version
👨‍💻 Author

VISHVANTH
B.Tech Student | Developer | Problem Solver

GitHub: https://github.com/vishva3019

📄 License

This project is for educational and academic use.
