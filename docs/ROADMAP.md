# Campus Retain 3.0 — Audit and Roadmap

## 1. Audit of 2.0 (as found)

**Shape:** a single `app.py` (Flask + Flask-SQLAlchemy) with 7 Jinja templates, deployed on
Vercel against Neon PostgreSQL. Tables: `user`, `item`, `claim` (plus `email_code` from the
security patch). One college only (Alliance University, domain `@ced.alliance.edu.in`,
pickup at the DOSS office), hard-coded in the code and templates.

**Working features carried forward:** org-email login, forgot-password by emailed code,
found-item reporting with photo, search, claim with ownership proof, admin approve / reject
with remarks, claim history on the admin page, item removal, maintenance mode, email + SMS
notifications, Vercel Analytics.

**Security issues found** (11 were patched in the 2.0 hot-fix, before this rebuild):
reset code readable from the session cookie; first login claimed any email; fallback secret
key; XSS through item names; claimant email trusted from the browser; plain-text password
fallback; public `/init-db`, `/test-email`, `/test-sms` (with a hard-coded phone number);
`.env` never loaded; claims overwriting each other; base64 photos up to 16 MB inside the
database; no CSRF protection.

**Architectural limits:** no tenancy (one college), single env-var admin account, no roles,
no migrations (only `db.create_all()`), no tests, no audit trail, claims had no status of their
own (the outcome of a rejected claim was not recorded), item deletion destroyed claim history,
photos stored as base64 text in Postgres, all college text hard-coded in the templates.

**Not inspected:** the live Neon database. Its schema is inferred from the 2.0 models; confirm
with `\d user`, `\d item`, `\d claim` before running the migration (see `docs/DEPLOYMENT.md`).

## 2. Phases

Each phase ships working, tested software. Nothing is marked done without tests.

| Phase | Scope | Status |
|---|---|---|
| **1. Secure multi-tenant foundation** | App factory + blueprints; College / Campus / Department / Role / Permission / User / Item / ItemImage / Claim / Notification / CollectionPoint / Event / AuditLog / Subscription / PlatformSettings / EmailCode models; Alembic migrations including an in-place upgrade path for the 2.0 database; verified college-email registration routed by email domain; per-college branded login; hashed OTPs; account lockout; Flask-Limiter rate limits; Flask-WTF CSRF; security headers; session expiry and invalidation on password change; role-based permissions checked server-side; strict tenant scoping on every query; per-claim status with full history; soft removal instead of destructive delete; audit log; in-app notification records; health check; minimal platform page to create, activate and suspend colleges; CLI for colleges, users and legacy adoption; pytest suite on PostgreSQL. | **Done** |
| **2. Storage, collection and pickup** | Cloudflare R2 behind a storage interface (R2 / local folder / in-memory / 2.0 database fallback); up to 3 compressed photos per item; `flask storage move-legacy-photos` moves 2.0 base64 photos out of Postgres; private bucket, photos served only to signed-in members of the same college through short-lived signed URLs; collection points managed by college admins; one-time pickup code emailed on approval, checked at the Security Staff pickup desk (attempt limit, expiry, resend); handover records; lost-item reports with an "I found this" match that alerts the owner; My activity page (claims, reports, notifications, withdraw claim, close lost report). | **Done** |
| **3. React frontend** | Vite + React 19 + TypeScript + Tailwind 4 + Motion (Framer Motion) + Lucide in `frontend/`, built into `static/app` and served by Flask at `/app/` (same origin, session cookie + CSRF). JSON API `/api/v1`. Pages: browse found items and lost reports (search, category filter, pagination), report found/lost with up to 3 photos, claim, My activity (claims with pickup details, reports, notification centre), admin dashboard (counts, kind/status/category filters, search, approve/reject with remarks, remove, move collection point, CSV export), pickup desk, collection points, platform colleges. Light, dark and system themes; phone bottom tab bar; keyboard-accessible dialogs. Sign-in, sign-up and password reset stay server-rendered; the classic pages still work as a fallback. | **Done** |
| **4. Analytics and exports** | Analytics from real rows only (recovery rate, median/average days to pickup, monthly found/lost/returned, by category, campus and collection point, claim outcomes, backlog), with the definitions shown to admins; Excel workbook and PDF report; CSV export; college and platform activity log; platform-wide stats per college. Empty data shows "–", never an invented rate. | **Done** |
| **5. Matching and AI** | Without AI: PostgreSQL trigram matching of found items to lost reports (owners alerted, can dismiss; confirmed when a claim is approved), duplicate-report warning before posting, typo-tolerant full-text search, rule-based claim warnings for reviewers. With Claude (optional, needs `ANTHROPIC_API_KEY`, Premium plan): photo-to-description suggestions the reporter edits, and an AI second opinion on a suggested match. Structured output, server-side fallbacks, rate-limited and audit-logged. AI only suggests; people decide. | **Done** |
| **6. Inter-college network and events** | Opt-in network: redacted listings (name, category, date, college only), cross-college claims reviewed and handed over by the item's college, audit entries. Event portals with QR posters. QR item tags with an anonymous "message the owner" page. Approximate (~100 m) item locations on an OpenStreetMap map. | **Done** |
| **7. Plans and production hardening** | Free / Standard / Premium plans assigned by hand with payment references (no payment provider), feature gates and limits, expiry falls back to Free. PostgreSQL row-level security on college-owned tables, tested as a restricted role. Redis rate-limit storage via `REDIS_URL`. Sentry with personal data stripped. Backups and restore runbook. Browser push notifications (Web Push). | **Done** |
| **Onboarding (after 7)** | Animated public welcome at `/`, college picker (Alliance University `@ced.alliance.edu.in`, MVJ College of Engineering `@mvjce.edu.in`, Vemana Institute of Technology `@vemanait.edu.in`, configured as data and listed by the platform admin), step-by-step student details (name, USN, department, year, password with strength meter), 6-digit email code with paste, countdown and resend, success screen. The account is created only after the code is confirmed. React sign-in with college selection, fixed email domain, "keep me signed in" for students, forgot password and one-time email confirmation for older accounts. Exact-domain checks on the server, enumeration-safe responses, rate limits, prefers-reduced-motion respected. | **Done** |
| **UX polish** | Student home built around find / report / track (search, Found and Lost tabs, filters for category, campus, date, status and place, item details with photos and a claim button, privacy-safe fields only); guided reporting (choose, details, review, confirmation with reference number, matching found items shown after a lost report); matching skips found-before-lost pairs; claim timeline (submitted, under review, approved, awaiting pickup, returned or not approved) with pickup place, instructions and an in-app pickup code; My activity with claims, reports and recovered items; notification centre with read/unread and links to the claim or item; daily pickup reminders; admin claims queue with proof beside the private detail and claimant history; campus filter; handover confirmation at the desk; welcome page lists the colleges and a privacy note. | **Done** |

## 3. Decisions needed from you (later phases)

- **Phase 2:** chosen: Cloudflare R2. You need to create the bucket and API token (docs/DEPLOYMENT.md).
- **Phase 5:** chosen: Claude. You need an Anthropic API key (paid per use).
- **Phase 7:** chosen: manual plans (no payment provider). Online payment (e.g. Razorpay) can be
  added later. Redis (Upstash), Sentry and VAPID keys are yours to create.
- **Hosting:** Vercel works for Phase 1–3. Background jobs (AI embeddings, reminders) will need
  either Vercel Cron + a queue or a small always-on worker (Render / Railway / Fly.io).
