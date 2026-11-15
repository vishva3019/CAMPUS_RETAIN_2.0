CAMPUS RETAIN 3.0 – FULL WEBSITE PROMPT

Act as a senior SaaS architect, full-stack engineer, security engineer and product designer.
Build (or rebuild) Campus Retain 3.0 exactly as specified below: a secure, multi-college
lost-and-found platform for colleges in Bengaluru, Karnataka, India.

Tagline: "One Platform. Multiple Colleges. One Connected Campus Community."

Every feature must really work: no dummy data in production, no fake statistics, no fake AI,
no buttons without actions, no frontend-only security. Test every important flow.

Product goal: it should feel effortless. A student understands what to do immediately,
reports a found item in under a minute, finds missing belongings quickly and tracks a claim
without confusion. An administrator reviews claims and manages handovers without
complicated navigation. Prioritise usability, trust, speed, clarity and reliability over the
number of features. Do NOT add social feeds, chat, leaderboards, reward points, chatbots,
public student directories, complicated profiles, excessive analytics or unnecessary pop-ups.

------------------------------------------------------------------------------------------
1. TECHNOLOGY
------------------------------------------------------------------------------------------
Backend
- Python, Flask app factory with Blueprints, Flask-SQLAlchemy (SQLAlchemy 2), Alembic
  migrations (Flask-Migrate), PostgreSQL on Neon (psycopg 3).
- Flask-WTF CSRF (form field on pages, X-CSRFToken header on JSON calls), Flask-Limiter
  (Redis storage in production via REDIS_URL), werkzeug password hashing.
- Gmail SMTP for email (console backend locally), optional Twilio SMS, optional Web Push
  (pywebpush + VAPID), optional Sentry (personal data stripped).
- Cloudflare R2 (S3 API via boto3) for photos, in a private bucket.
- Claude (Anthropic API) for optional AI features. Default model: claude-opus-5-5.
- openpyxl (Excel), fpdf2 (PDF), segno (QR codes), pg_trgm for fuzzy text matching.

Frontend
- React 19 + TypeScript + Vite 6 + Tailwind CSS 4 + Motion (Framer Motion) + Lucide icons
  + React Router 7, in frontend/. Built into static/app and served by Flask at /app/
  (same origin, session cookie). The signed-in app is code-split and lazy-loaded so the
  public welcome screen loads fast. Leaflet + OpenStreetMap for the map.
- Classic server-rendered Jinja pages remain as a fallback and for staff sign-in.

Hosting
- Vercel (Python runtime) + Neon. The React build is committed (no Node step on Vercel).

------------------------------------------------------------------------------------------
2. MULTI-TENANCY AND ROLES
------------------------------------------------------------------------------------------
- One deployment, unlimited colleges. Every college-owned row (items, claims, photos,
  matches, collection points, events, campuses, QR tags) carries college_id.
- All queries are scoped to the signed-in user's college on the server. Another college's
  ids return 404. The browser's college_id is never trusted.
- PostgreSQL row-level security as a second layer: each transaction sets
  app.college_id; policies hide other colleges' rows. The app connects as a restricted
  role (no BYPASSRLS); migrations run as the owner. Cross-college reads are only allowed
  inside an explicit, audited bypass (the inter-college network).
- Roles and permissions (checked on the server for every page and API call):
  - Platform Super Admin: colleges, plans, platform analytics and audit. No college data.
  - College Admin: claims, listings, collection points, analytics, exports, settings,
    events, audit, pickup desk.
  - Campus Moderator: claims and listings for their campus.
  - Security Staff: pickup desk only (verify codes, hand over items).
  - Student: browse, report found/lost, claim, track, QR tags.

------------------------------------------------------------------------------------------
3. COLLEGES AND ONBOARDING
------------------------------------------------------------------------------------------
Colleges are data, not code. Each has name, slug, short name, city, status
(pending / active / suspended), brand colour, logo URL, email domains, support office,
pickup instructions, contact email, inter-college opt-in and "listed on sign-up".

Initial colleges on the sign-up screen (exact domain match, no subdomains):
- Alliance University – @ced.alliance.edu.in
- MVJ College of Engineering – @mvjce.edu.in
- Vemana Institute of Technology – @vemanait.edu.in
Set up with an idempotent command:
  flask college onboard --name ... --slug ... --domain ... [--color] [--logo-url]
Platform admins can show or hide any active college on the sign-up screen.

Animated onboarding (public, React):
1. Welcome (/): "Welcome to Campus Retain", the tagline, "Lost something on campus? Found
   something that belongs to someone else? We're here to reconnect people with their
   belongings.", a glowing "Get Started" button, "Already have an account? Sign in",
   three feature cards, and "Your campus. Your community. Your belongings."
2. Select College (/app/join): "Which college do you belong to?" with one card per listed
   college (monogram or logo, name, city, @domain), hover lift, selected tick, then an
   automatic move to the form.
   The welcome page also lists the colleges it serves ("Open to students of", with monograms)
   and a privacy note: "Only verified college emails can join. Your contact details are never
   shown to other students."
3. Student Details, in three short parts: (a) full name + college email, where the student
   types only the part before "@" and the college's domain is fixed after it; (b) student
   ID / USN, department (free text with suggestions from that college's departments),
   year of study (1st, 2nd, 3rd, 4th, Other); (c) password + confirm with show/hide and a
   strength meter. Inline validation everywhere.
4. Verify Email: six digit boxes (auto-advance, paste, backspace), expiry countdown, resend
   after 60 seconds, clear errors, shake on a wrong code.
5. Account Created: animated tick, "You're officially connected!", name, college, verified
   email, "Enter My Campus" to the college dashboard.
A five-step progress bar shows throughout. Progress survives a refresh (never passwords).

Rules
- Email is normalised and must end in the selected college's domain, checked in the
  browser and again on the server from the college record. The error names the college:
  "Please enter your official Alliance University email address ending with
  @ced.alliance.edu.in."
- The account row is created only after the code is confirmed; form details wait in a
  pending-registration table (expires in 2 hours).
- Signing up with an email that already has an account gives the same on-screen response
  and emails the owner instead (no account enumeration). One account per USN per college.
- Codes: 6 digits, stored hashed, 10-minute expiry, 5 wrong tries, a new code cancels the
  old one, 60-second resend wait, never in responses. Rate limits per IP.

Sign-in (/app/signin): choose college, college email (fixed domain) and password,
"Keep me signed in for 30 days" (students only; staff always expire after 8 hours,
enforced on the server), forgot password (code + new password), one-time email
confirmation for older accounts, 5 wrong passwords lock the account for 15 minutes.
Staff without a college-domain email and platform admins use /admin_login.
Signed-in users who open /, /app/join or /app/signin go straight to their dashboard.

------------------------------------------------------------------------------------------
4. LOST AND FOUND (STUDENT EXPERIENCE)
------------------------------------------------------------------------------------------
Student home, built around three tasks: find something I lost, report something I found,
track my reports and claims.
- Banner "Lost it? Find it." with the student's real college name, a search box ("Search
  items") that matches item name, category, description and place (typo-tolerant), a hint
  line, and two buttons: "Report an item" and "Track my claims and reports".
- Tabs: Found items / Lost reports. List or map view. Events link when an event is open.
- Filters panel: category, campus (when the college has campuses), date reported (today,
  7 days, 30 days, 3 months), status for found items (Not yet returned [default], Available
  to claim, Returned, All) and place. "Clear" resets everything.
- Item cards (2 per row on phones, 4 on desktop): real photo, status badge in plain words
  (Available, Claim under review, Awaiting pickup, Returned, Lost), category, name, place,
  date, "View details". The whole card opens the details.
- Item details (modal, deep-linkable as /app/?item=<id>): photo gallery, reference
  (F-00006 / L-00045), category, found/lost date, reported date, place and campus, where
  it's held (collection point and hours), public description, the student's own claim status
  with a link to track it, and the right action: "This is mine" (claim) or "I found this"
  (for lost reports). Never shown to students: private identifying detail, reporter's
  email, phone numbers, staff notes.
- Empty states: "No items have been reported yet. Be the first to report something." (with
  a Report button), "Nothing matches" with a clear-filters link. Loading skeletons, error
  messages with retry, success toasts.

Quick reporting (modal, mobile-friendly):
1. "What would you like to do?" with two cards: I found something / I lost something.
2. Details: optional photos (up to 3, AI suggestion if enabled), item name, category, date,
   place (+ optional approximate map location for found items), description; for found
   items also the collection point it was handed in to (if the college has any) and a
   private identifying detail visible only to staff; event and campus when relevant. Inline
   validation; duplicate warning ("Already reported? These look similar").
3. Review: everything as students will see it, the private detail marked "Only staff see
   this", Edit or Submit.
4. Confirmation: reference number, "saved in My activity", how many likely owners were
   alerted, hand-in reminder; after a lost report, found items that already look similar.

Photos: validated, resized to 1600 px JPEG, metadata stripped, max 5 MB each, stored in
private R2, shown only to signed-in members of the same college through 5-minute signed
links. Old base64 photos can be moved to R2 with a command.

Claims: student ID / USN (prefilled from registration), optional phone, ownership proof.
One active claim per item (database-enforced). Full history kept. Students can withdraw a
claim still under review.

Claim tracking (My activity → My claims, Active and History):
- Timeline: Submitted → Under review → Approved → Awaiting pickup → Returned, or
  Not approved / Withdrawn. Submission date, reference, staff remarks.
- When approved: collection point (name, campus, hours, directions), pickup instructions,
  and "Show my pickup code", which issues a fresh 6-digit code, shows it once to the
  signed-in claimant and emails it (only a hash is stored; older codes stop working;
  60-second wait between codes; valid 14 days; 5 wrong tries at the desk).
- Students never need to contact staff to learn their claim status.

My activity has three tabs: My claims (active + history), My reports (things I lost, things I
found, with status, "I got it back" / "Remove" for open lost reports, and suggested matches
with "Not mine"), and Recovered (items returned to me with the date, and lost reports I
marked as found).

Notification centre (/app/notifications, bell in the header): read/unread dots, timestamps,
"Mark all as read", opening a notification marks it read and goes to the exact claim or item,
"You're all caught up!" when empty, optional browser push. Only important events: possible
match, claim submitted, approved (pickup code ready), not approved, pickup reminder,
returned, and "returned to its owner" for finders.

Pickup reminders: one in-app + email reminder when an approved item isn't collected after
PICKUP_REMINDER_DAYS (3). Runs daily via Vercel Cron (/internal/cron/pickup-reminders with
"Authorization: Bearer CRON_SECRET", disabled without the secret) or
"flask claims remind-pickups".

Soft removal of listings; nothing is hard-deleted.

------------------------------------------------------------------------------------------
5. MATCHING AND AI
------------------------------------------------------------------------------------------
Without AI (always on):
- New found items are compared with open lost reports on name, category, description,
  place and date (pg_trgm + full-text, weighted score). A pair is skipped when the item was
  found more than a day before it was lost. Likely owners get an email and an alert linking
  to the item and can dismiss with "Not mine". Staff see each match with its real text-match
  percentage. Matches are confirmed when a claim is approved.
- Duplicate warning before posting a report.
- Rule-based claim warnings for reviewers (e.g. repeated rejections, proof that copies
  the public listing).
With Claude (needs ANTHROPIC_API_KEY, Premium plan):
- "Suggest details from photo": name, category and a non-identifying description that the
  reporter edits.
- "Ask AI" on a suggested match: likely / unlikely / unsure with a reason, for staff.
- Structured output, server-side fallbacks, refusal and length checks, rate limit per
  user (30 per hour), audit log. AI only suggests; people always decide.

AI search and chatbot (Claude; both also work without a key in a rules-only "basic" mode):
- Student home hero (screenshot-style, Ivory & Forest): pill "<College> · Lost & Found ·
  AI-assisted", headline "Lost something? AI helps you find it." (basic mode: "Let's find
  it."), honest sub-copy, buttons Browse catalog / Report lost item / I found something, a
  "Describe what you lost" box with "Search with AI" and example chips, "Track my claims".
- Search with AI (/api/v1/search/smart): Claude turns the sentence into keywords, category,
  place and time window (rules do the same in basic mode); a real query over the student's
  college runs it, loosening one guess at a time (category, then place, then date) and
  saying what it widened. Shows "AI understood: …" chips and item cards, or "Report it as lost".
- Campus Retain AI chatbot: floating button on every member page (above the phone tab bar),
  bottom-sheet on phones, panel on desktop. Suggested prompts, typing indicator, item result
  cards that open item details, new-conversation button, "The assistant can make mistakes.
  Staff decide every claim." Conversation kept only in the browser tab. Answers come only from
  real candidate items of the student's college (public fields only) and the student's own
  claims; invented item IDs are dropped; private details, reporter/claimant contacts and staff
  notes are never sent to the model; it cannot approve or change anything. Intents: search,
  claim status, how to claim, how to report found/lost, pickup, greeting. Rate-limited
  (ASSISTANT_RATE_LIMIT, 60/hour per user); AI use is audit-logged (message length only).

------------------------------------------------------------------------------------------
6. NETWORK, EVENTS, QR TAGS, MAP
------------------------------------------------------------------------------------------
- Inter-college network (opt-in, plan-gated): redacted listings (item, category, date,
  college only); claims go to the college holding the item and are handed over at its desk.
- Event portals (fests, hackathons, sports): own item list and a QR poster.
- QR stickers: students print tags for belongings; whoever scans one can message the owner
  without seeing their name or email (public page /t/<code>, rate-limited).
- Map of found items with approximate locations (OpenStreetMap tiles).

------------------------------------------------------------------------------------------
7. DASHBOARDS
------------------------------------------------------------------------------------------
Student: welcome banner "Lost it? Find it." with college name and search, found items and
lost reports, report button, My activity, QR tags, events, network, notifications.
College admin main page (no charts):
- Four stats: Available items, Claims to review, Awaiting pickup, Open lost reports.
- "Claims to review" queue (oldest first): the item (photo, reference, category, place,
  date, held at, public description, and the PRIVATE DETAIL highlighted) beside the claim
  (claimant email, ID, phone, college if via the network, submitted time, ownership proof),
  rule-based warnings, the claimant's other claims and earlier claims on the same item.
  Approve (optional note) or Reject with a required reason. "You're all caught up" when empty.
- All items: Found / Lost tabs, search, status, category and campus filters, pagination,
  collection-point assignment, remove listing, claim history per item, possible matches
  (with optional AI check), CSV export.
- Tool links: pickup desk, analytics, collection points, events, settings, activity log.
Pickup desk: list of approved claims waiting, search; staff enter the student's code, then
confirm "I've checked their college ID card" before the handover; the item becomes Returned
(never shown as available again), the handover is recorded with the staff member's name and
in the audit log, and the student and finder are notified.
Analytics (real rows only, "–" when empty): recovery rate, median and average days to
pickup, monthly found/lost/returned, by category, campus and collection point, claim
outcomes, backlog, date presets and custom range; Excel and PDF exports; definitions shown.
Platform: colleges (create, activate, suspend, invite admins, show on sign-up), totals and
recovery by college, plans, platform activity log.

------------------------------------------------------------------------------------------
8. PLANS
------------------------------------------------------------------------------------------
Assigned by hand by the platform admin with an invoice/UTR reference (no payment gateway):
- Free: core lost and found, 2 collection points.
- Standard: + analytics, exports, events, network; 10 collection points.
- Premium: everything including AI; unlimited collection points.
- Pilot (no plan assigned yet): everything on. Expired plans fall back to Free.

------------------------------------------------------------------------------------------
9. DESIGN: "IVORY AND FOREST"
------------------------------------------------------------------------------------------
- Background ivory #faf8f3; surfaces white; warm stone greys; accent forest green
  (#166534, ramp brand-50 #eff8f1 … brand-950 #072414); soft green and gold background glows.
- Fonts: Fraunces (serif) for headings, Source Sans 3 for everything else.
- Logo: forest-green rounded square with a returning-loop mark; wordmark "Campus Retain"
  with "Retain" in green.
- Light and dark mode (warm near-black with green accents) plus "system".
- Subtle Motion animations: page and step transitions, card hover, success tick; all
  respect prefers-reduced-motion. Loading skeletons, empty states, toasts, accessible
  dialogs, visible keyboard focus.

------------------------------------------------------------------------------------------
10. PHONES
------------------------------------------------------------------------------------------
- Every page works at 375, 390, 768 px and desktop with no sideways scrolling.
- Bottom tab bar on phones; header shows the logo, "Campus Retain" and the college name.
- Item cards two per row on phones; long forms and dialogs keep their buttons pinned to the
  bottom; dialogs are bottom sheets on phones; images lazy-load.
- Form fields use 16 px text on phones (no iPhone zoom); links and buttons have
  comfortable tap areas; safe-area padding at the bottom.

------------------------------------------------------------------------------------------
11. SECURITY AND OPERATIONS
------------------------------------------------------------------------------------------
- CSRF everywhere, rate limits, security headers (CSP, frame denial, nosniff, HSTS),
  HttpOnly SameSite=Lax secure cookies, session invalidation on password change, safe
  error pages, no public setup or test endpoints, refuses to start in production without
  SECRET_KEY and DATABASE_URL, secrets only in environment variables.
- Audit log of sign-ins, registrations, resets, reports, claims, reviews, handovers, plan
  and college changes, AI use and cross-college access.
- Migrations 0001–0010 (0009 onboarding, 0010 pickup reminders).
- /healthz for uptime monitoring; backup and restore runbook; migration guide for the 2.0
  database (back up first, rehearse on a Neon branch, then production).

------------------------------------------------------------------------------------------
12. TESTING
------------------------------------------------------------------------------------------
- pytest on real PostgreSQL: registration for each college, wrong and Gmail domains,
  direct API bypass, duplicates, invalid/expired codes, resend limits, sign-in, college
  switching, remember-me, session expiry, password reset, permissions, tenant isolation,
  row-level security as a restricted role, claims, pickup codes, photos (R2 via moto),
  matching, AI (fake client), network, events, tags, plans, exports, rate limits,
  migrations from the 2.0 schema.
- Polish features: filters, item-details privacy, report references and suggestions,
  found-before-lost matching, claim stages, in-app pickup code, notification links, admin
  review queue isolation, pickup reminders and cron authentication.
- vitest for the React app (email rules, password strength, code input, item cards,
  components). Current totals: 180 pytest, 24 vitest.
- Browser checks at 375, 390, 768 and 1440 px (no overflow, no console errors).

Deliver working, tested software with clear docs (README, DEPLOYMENT, RUNBOOK, ROADMAP).
Never commit secrets. Never run destructive migrations on production without approval
and a backup. Never claim something is deployed or working unless it was verified.
