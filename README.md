# Campus Retain AI 🎒🤖

> **Find what you lost, faster with AI.**  
> *Official Entry for the Razorpay AI Builder Internship 2026 / Buildathon*

**Live Deployment:** [https://campus-retain-2-0.vercel.app/](https://campus-retain-2-0.vercel.app/)  
**Website:** [https://campusretain.in](https://campusretain.in)

---

## 📌 Problem Statement

Every semester, thousands of personal assets — laptops, smartphones, water bottles, calculators, ID cards, and keys — are misplaced across university campuses. Traditional lost-and-found methods rely on manual bulletin boards or static spreadsheets:
- **Keyword Mismatch**: A student searching for *"navy blue school bag"* fails to find a post titled *"blue backpack"*.
- **Delayed Recovery**: Found items sit in custody for weeks because students don't know who has them or where to look.
- **Verification Fraud & Overhead**: Administrators struggle to verify whether a claimant is the true owner without exposing confidential identifiers.

---

## 💡 The Solution: Campus Retain AI

**Campus Retain AI** transforms the campus lost-and-found workflow into an intelligent, multimodal ecosystem that pairs lost reports with discovered items in real time, understands conversational human search, and assists administrators with fraud-resistant claim verification.

---

## 🤖 Core AI Capabilities

### 1. Multimodal AI Image Analysis
When a student or staff member uploads a photo of a found or lost item:
- **Automatic Attribute Extraction**: Identifies category, primary & secondary colors, brand, model, visible text, and distinctive visual characteristics (e.g. *"red zipper on front pocket"*, *"sticker on left bezel"*).
- **Form Auto-Fill**: Auto-populates title and category dropdowns, reducing manual data entry friction.
- **Confidence Scoring**: Assigns an objective AI confidence rating to the extracted metadata.

### 2. Multi-Factor Lost & Found Matching Engine
When a lost item is reported, the matching engine immediately cross-references all active found reports (and vice versa):
- **Weighted Multi-Factor Scoring**: Category (25%), Color & Color Families (20%), Brand/Model (15%), Keyword Overlap (20%), Distinctive Visual Features (10%), Location Proximity (5%), and Date Proximity (5%).
- **Semantic Reasoning & Evidence**: Provides clear, human-understandable matching reasons (e.g., `✓ Same category (Backpack)`, `✓ Same brand (Nike)`, `✓ Matching feature (Red zipper)`) and notes discrepancies.
- **Confidence Hierarchy**: Color-coded badges for *Likely Match* (80–100%), *Potential Match* (60–79%), and *Possible Match* (40–59%).

### 3. Natural Language Search
Allows students to describe their lost property using natural conversational language:
- **Semantic Query Understanding**: Translates unstructured sentences (*"I lost my black Nike backpack near the library yesterday"*) into structured entity parameters without guessing unstated fields.
- **Dynamic Relevance Ranking**: Ranks real database inventory by relevance percentage (*94% Relevant - High Relevance*) and displays match justifications.
- **Interactive UI Pills**: 1-click sample search queries for immediate discovery.

### 4. AI-Assisted Claim Verification
Assists campus administrators in evaluating ownership claims without replacing human authority:
- **Privacy-Preserving Proof Assessment**: Compares claimant proof descriptions against item metadata and hidden secret details server-side without leaking secrets.
- **Strict Anti-Hallucination Guardrail**: The AI recommendation is strictly locked to `MANUAL ADMIN REVIEW` — the AI never automatically approves or rejects claims.
- **Evidence Breakdown**: Displays matching factors, conflicting factors, and a neutral summary in the administrator dashboard.

### 5. Campus Retain AI Conversational Assistant
A floating chat assistant that guides students across the platform:
- **Grounded Inventory Search**: Responds only with real database records; strictly refuses to fabricate non-existent items.
- **Workflow Guidance**: Explains claiming steps, reporting found items (with physical handover to the DOSS office), and tracking lost reports.
- **Anti-Theft Security Shield**: Politely refuses to disclose secret verification details or administrator credentials.

---

## 👨‍🎓 Student Portal & 👨‍💼 Admin Operations

### 👨‍🎓 Student Features
- **Secure Domain Authentication:** Identity protection strictly matching campus organization emails (`@ced.alliance.edu.in`).
- **Multimodal Discovery Registry:** Instantly report found items with AI visual attribute extraction, category mappings, and location coordinates.
- **Instant Match Discovery:** Report lost items to automatically trigger matching against all active found records.
- **Dynamic NL Search & Filters:** Type natural conversational queries or filter by category and location in real-time.
- **Possession Claim Pipeline:** Submit unique identifier attributes (proof description) that only the true owner would know.
- **Password Recovery:** Secure email-based OTP (One-Time Password) workflow to reset account credentials if forgotten.

### 👨‍💼 Administration Features
- **Cyber-Dark Operations Terminal:** Premium dark-themed administrative dashboard providing live metrics (Total Records, AI Potential Matches, Pending Reviews, Successfully Claimed).
- **Dual Decision Engine:**
  - **Approve Claim:** Marks an asset as securely handed over and locks its public status to `Claimed`.
  - **Reject Claim:** Prompts the admin for custom rationale remarks, instantly alerts the student, and returns the asset to `Available` status for public discovery.
- **AI Verification Cards:** Inspect AI confidence ratings, matching factor breakdowns, and conflicting attributes for each pending claim.
- **Claim History Audit Logs:** A clean chronological feed showing past claim attempts, historical proof inputs, and user coordinates for every item.
- **Resolution Cleanup:** Permanent item deletion capabilities to manage active warehouse inventory.

### 🔔 Integrated Notifications
- **Email Dispatch Pipeline:** Automated secure SMTP notifications triggering on Account Registration, Claim Submissions, Approvals, and Rejections (including admin remarks).
- **Cellular SMS alerts:** Twilio API integration providing immediate SMS alerts straight to the student's phone.

---

## 🏗️ System Architecture

```mermaid
flowchart TD
    subgraph Client Layer
        A[Student Web UI] -->|Photo Upload| B[Multimodal Vision Endpoint]
        A -->|Natural Language Query| C[Semantic Search Endpoint]
        A -->|Chat Message| D[AI Assistant Endpoint]
        A -->|Submit Claim| E[Claim Endpoint]
        F[Admin Control Terminal] -->|Review Verification| G[Admin Approval/Rejection]
    end

    subgraph Backend Core [Flask 3 + SQLAlchemy 2]
        B --> H[ai/vision.py]
        C --> I[ai/search.py]
        D --> J[ai/assistant.py]
        E --> K[ai/claims.py]
        
        H --> L[AI Client REST Gateway]
        I --> M[Matching & Scoring Engine]
        K --> M
        J --> I
    end

    subgraph External Services & Storage
        L -->|REST| N[Google Gemini 1.5 Flash / OpenAI]
        H -->|Storage| O[Cloudinary Image CDN]
        Backend Core --> P[(PostgreSQL Neon DB / SQLite)]
        E -->|Alerts| Q[SMTP Email & Twilio SMS]
    end
```

---

## 🛠️ Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Frontend** | HTML5, Tailwind CSS 4, Vanilla JS, Animate.css | Ultra-responsive, glassmorphism UI |
| **Backend** | Python 3.11+, Flask 3.1.3, Werkzeug 3.1.8 | Modular REST API & web server |
| **ORM & DB** | SQLAlchemy 2.0, Flask-SQLAlchemy, PostgreSQL (Neon) / SQLite | High-performance relational database |
| **AI Layer** | Google Gemini 1.5 Flash REST API, OpenAI API | Vision, Semantic Reasoning, Search, Chat |
| **Storage & Media** | Cloudinary CDN, Base64 Fallback | Secure image hosting & CDN delivery |
| **Messaging** | SMTP (TLS), Twilio SMS | Automated student & admin notifications |
| **Hosting** | Vercel Serverless WSGI | Global edge deployment |

---

## 📂 Project Structure

```text
CAMPUS_RETAIN_2.0/
├── ai/                         # Modular AI Layer
│   ├── __init__.py
│   ├── assistant.py            # Conversational AI Assistant & Intent Router
│   ├── claims.py               # AI Claim Verification Assistance
│   ├── client.py               # Unified AI Client (Google Gemini / OpenAI / Mock)
│   ├── config.py               # Central AI Configuration & Safety Settings
│   ├── exceptions.py           # Typed AI Exception Hierarchy
│   ├── matching.py             # Multi-Factor Matching Engine & Scoring
│   ├── search.py               # Natural Language Search & Query Understanding
│   └── vision.py               # Multimodal Image Analysis & Metadata Extraction
│
├── app.py                      # Flask Application Entrypoint & API Routes
├── app/                        # Application Package
│   ├── __init__.py
│   └── models.py               # Declarative SQLAlchemy Database Models
│
├── templates/                  # Jinja2 Templates
│   ├── index.html              # Public Catalog, AI Search, Lost Reporting, AI Chat
│   ├── dashboard.html          # Internal Authenticated Student Dashboard
│   ├── admin.html              # Admin Dashboard, Discovered Pairs, Claim Logs
│   ├── login.html              # Student & Organization Login
│   ├── admin_login.html        # Secure Admin Gateway
│   ├── reset_password.html     # OTP Password Reset
│   └── maintenance.html        # Clean Maintenance Page
│
├── tests/                      # Comprehensive Unit & Integration Test Suite
│   ├── test_ai_architecture.py # AI Client & Config tests
│   ├── test_ai_vision.py       # Vision & image analysis tests
│   ├── test_ai_matching.py     # Deterministic & AI matching engine tests
│   ├── test_ai_search.py       # Natural language search tests
│   ├── test_ai_claims.py       # Claim verification & privacy tests
│   ├── test_ai_assistant.py    # Assistant intent & hallucination tests
│   └── test_e2e_workflow.py    # Full end-to-end user lifecycle tests
│
├── requirements.txt            # Pinned Production Dependencies
├── vercel.json                 # Vercel Serverless Deployment Manifest
├── .env.example                # Sample Environment Variables Reference
└── README.md                   # Project Documentation
```

---

## ⚙️ Installation & Local Setup

### 1. Clone the Repository
```bash
git clone https://github.com/vishva3019/CAMPUS_RETAIN_2.0.git
cd CAMPUS_RETAIN_2.0
```

### 2. Create and Activate Virtual Environment
```bash
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate

# Windows
python -m venv .venv
.venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Fill in your configuration keys in `.env`:
```env
SECRET_KEY=your-random-secret-key
DATABASE_URL=sqlite:///campusretain.db

AI_PROVIDER=google
AI_API_KEY=your-google-gemini-api-key
AI_MODEL=gemini-2.5-flash

ADMIN_EMAIL=admin@ced.alliance.edu.in
ADMIN_PASSWORD=your_admin_password
```

### 5. Run the Application
```bash
python app.py
```
Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

---

## 🧪 Running Tests

Execute the complete test suite across all AI modules and end-to-end user journeys:
```bash
python -m unittest discover tests
```

---

## 🔒 Privacy, Safety & Security Safeguards

1. **Zero Secret Leakage**: Raw secret identifying details (`secret_detail`) are never exposed in public search responses, browser consoles, assistant chat, or URLs.
2. **Server-Side Secret Verification**: Exact secret comparisons occur server-side; the AI model is never asked to "guess" secret answers.
3. **No Automated Decisions**: The AI operates exclusively in an advisory capacity. Claim approval or rejection is strictly reserved for human administrators.
4. **Offline Deterministic Fallbacks**: If the AI provider is unavailable, unconfigured, or rate-limited, all features (search, matching, claim scoring, assistant) gracefully fall back to local deterministic algorithms with zero downtime.
5. **Role-Based Access Control**: Sensitive administrative endpoints (`/api/admin/*`) require authenticated administrator sessions.

---

## 🌐 Production Deployment

The application is configured for deployment on **Vercel** serverless infrastructure using PostgreSQL (Neon DB).

1. Push your repository to GitHub.
2. Import the project into Vercel.
3. Set environment variables (`SECRET_KEY`, `DATABASE_URL`, `AI_PROVIDER`, `AI_API_KEY`, `ADMIN_EMAIL`, etc.).
4. Deploy!

---

## 👨‍💻 Author & Acknowledgments

**VISHVANTH**  
*B.Tech Student & Developer | Alliance University*  
GitHub: [https://github.com/vishva3019](https://github.com/vishva3019)  
Live Application: [https://campus-retain-2-0.vercel.app/](https://campus-retain-2-0.vercel.app/)

*Developed for the Razorpay AI Builder Internship 2026 / Buildathon.*
