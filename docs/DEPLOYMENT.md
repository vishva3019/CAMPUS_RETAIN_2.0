# Deploying Campus Retain 3.0

## Requirements

- Python 3.11+ (Vercel's Python runtime is fine)
- PostgreSQL 14+ (Neon). SQLite is **not** supported: the migrations and the
  one-active-claim index are PostgreSQL features.
- Gmail (or any SMTP) account with an App Password for outgoing email
- Cloudflare account with an R2 bucket for item photos (free tier: 10 GB storage)
- Optional: Twilio for SMS; Redis for shared rate limits

## Environment variables

See [`.env.example`](../.env.example). In production the app **refuses to start** without
`SECRET_KEY` (32+ characters) and `DATABASE_URL`. `postgres://` and `postgresql://` URLs are
rewritten to the psycopg 3 driver automatically.

| Variable | Required | Notes |
|---|---|---|
| `SECRET_KEY` | yes | `python -c "import secrets; print(secrets.token_hex(32))"`. Changing it signs everyone out. |
| `DATABASE_URL` | yes | Neon **pooled** connection string with `sslmode=require`. |
| `APP_ENV` | no | `production` on Vercel automatically. |
| `MAIL_BACKEND` | no | `smtp` in production (default). |
| `MAIL_USERNAME`, `MAIL_PASSWORD` | for email | Without them, no verification codes are sent and nobody can register. |
| `RATELIMIT_STORAGE_URI` | recommended | `memory://` limits are per serverless instance. Use Redis (e.g. Upstash) for real limits. |
| `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET` | for photo storage | When `R2_BUCKET` is set, photos go to R2. Without R2, production keeps photos in the database as 2.0 did. |
| `STORAGE_BACKEND` | no | `r2`, `database`, or `local` (development only). Chosen automatically. |
| `REDIS_URL` | recommended | Shared rate limits across Vercel instances (Upstash free tier works). `RATELIMIT_STORAGE_URI` overrides it. |
| `ANTHROPIC_API_KEY` | for AI | Turns on photo-to-description and AI match checks (Premium plan). Paid per use. `AI_MODEL` defaults to `claude-opus-5-5`. |
| `ASSISTANT_RATE_LIMIT` | no | Default "60 per hour" per user, for the chatbot and "Search with AI". |
| `SENTRY_DSN` | recommended | Error monitoring. Cookies, headers, bodies, IPs and emails are stripped before sending. |
| `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT` | for push | Browser notifications. `flask --app app push vapid-keys` prints a pair. |
| `TWILIO_*` | no | SMS is skipped when unset. |
| `SESSION_HOURS` | no | Default 8. |
| `REMEMBER_DAYS` | no | Default 30. How long "Keep me signed in" lasts (students only). |
| `CRON_SECRET` | for reminders | Any long random string. Vercel Cron sends it to `/internal/cron/pickup-reminders` (daily, 09:00 IST, set in `vercel.json`). Without it the endpoint is switched off. |
| `PICKUP_REMINDER_DAYS` | no | Default 3. Approved items not collected after this many days get one reminder. |

The 2.0 variables `ADMIN_EMAIL` / `ADMIN_PASSWORD` are **no longer used**. Admins are real
accounts with roles (see "Accounts" below).

## Setting up Cloudflare R2 (photos)

1. Cloudflare dashboard → **R2** → **Create bucket**, e.g. `campus-retain-photos`. Leave
   public access **off**: the app serves photos itself, through signed links that expire in
   5 minutes, and only to signed-in members of the photo's college.
2. R2 → **Manage API tokens** → **Create API token** with *Object Read & Write*, limited to that
   bucket. Copy the **Access Key ID** and **Secret Access Key** (shown once) and your
   **Account ID**.
3. Set `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` and `R2_BUCKET` on Vercel
   (and in your local `.env` when running the commands below). Never commit them.
4. After deploying, move the photos 2.0 stored in the database into R2 (safe to stop and
   re-run; each item is committed on its own):
   ```
   flask --app app storage move-legacy-photos --dry-run
   flask --app app storage move-legacy-photos
   ```
   This makes the database much smaller. Items whose inline photo is broken are reported
   and left unchanged.

No CORS rules are needed: browsers only load photos through the app's `/media/...` links.

## Upgrading the existing 2.0 production database

All steps run from your own machine against Neon. Nothing here deletes data, but take a
backup first anyway.

1. **Back up.** In the Neon console create a branch of the production database (an instant
   copy you can restore from), or run
   `pg_dump "$DATABASE_URL" > campus-retain-2.0-backup.sql`.
2. **Check the live schema** matches what 3.0 expects (`user`, `item`, `claim`, optionally
   `email_code`):
   ```
   psql "$DATABASE_URL" -c '\d "user"' -c '\d item' -c '\d claim'
   ```
3. **Try it on the Neon branch first.** Point `DATABASE_URL` at the branch, run steps 4–7,
   and sign in. Only then repeat against production.
4. Install and add the multi-tenant tables and columns (additive only):
   ```
   pip install -r requirements.txt
   flask --app app db upgrade 0002_multi_tenant
   ```
5. Create the college that owns the existing data, then assign the 2.0 rows to it:
   ```
   flask --app app college create --name "Alliance University" --slug alliance \
       --domain ced.alliance.edu.in --support-office "DOSS office" \
       --pickup-instructions "Collect your item at the DOSS office with your college ID." --active
   flask --app app legacy adopt --slug alliance
   ```
   `legacy adopt` asks you to confirm the backup. It makes existing users students who must
   confirm their email once on next login. The latest claim of a Pending item stays pending,
   the latest claim of a Claimed item becomes approved, and every other 2.0 claim is kept as
   `closed`, because 2.0 never recorded their outcome.
6. Enforce tenancy (college_id NOT NULL, one active claim per item) and add the Phase 2
   pickup columns:
   ```
   flask --app app db upgrade
   ```
   This refuses to run while any item or claim has no college. Claims already approved in
   2.0 have no pickup code: the student sends one from **My activity** before collecting.
7. Create the accounts that replace `ADMIN_EMAIL`:
   ```
   flask --app app user create --email you@example.com --role platform_super_admin
   flask --app app user create --email doss@ced.alliance.edu.in --role college_admin --college alliance
   ```
8. On Vercel set `SECRET_KEY` and `DATABASE_URL`, keep the `MAIL_*` / `TWILIO_*` variables,
   remove `ADMIN_EMAIL` / `ADMIN_PASSWORD`, and redeploy.

For a **new, empty database**, steps 4–6 collapse into `flask --app app db upgrade`, then
step 7 and `flask --app app college create ... --active`.

## Phases 4–7: what to set up

Run `flask --app app db upgrade` (migrations 0005–0008, all additive except that 0007
switches on row-level security). Then:

1. **Database role for the app (row-level security).** Policies only bind a role that is
   not a superuser and has no `BYPASSRLS`. Neon's default owner role bypasses them, so
   create a separate role for the running app and keep the owner for migrations:
   ```sql
   CREATE ROLE campus_retain_app LOGIN PASSWORD '<generate a long one>' NOBYPASSRLS;
   GRANT USAGE ON SCHEMA public TO campus_retain_app;
   GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO campus_retain_app;
   GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO campus_retain_app;
   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO campus_retain_app;
   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO campus_retain_app;
   ```
   Put that role's pooled connection string in Vercel's `DATABASE_URL`; run migrations
   with the owner's URL from your machine. `pg_trgm` (migration 0005) must be allowed, which
   it is on Neon.
2. **Plans.** Every college starts on *Pilot* (everything on). Assign Free / Standard /
   Premium in the platform console under **Plans**, with the invoice or UTR reference.
3. **AI (optional).** Create an API key at console.anthropic.com, set `ANTHROPIC_API_KEY`.
   Requests use structured output and server-side fallbacks; each use is audit-logged
   (`ai.describe`, `ai.match_check`) and limited to `AI_RATE_LIMIT` per user.
4. **Push (optional).** Generate VAPID keys once, set the three variables. Changing the
   keys later makes every browser subscribe again. iPhones only receive web push when the
   site is added to the home screen.
5. **Sentry (optional, recommended).** Create a Flask project, set `SENTRY_DSN`.
6. **Redis (recommended).** Create an Upstash Redis database, set `REDIS_URL`.
7. **Map.** Uses OpenStreetMap's public tiles with attribution. That's fine for light
   use; for heavy traffic switch to a tile provider with an API key (their usage policy).

Backups and restores: see [RUNBOOK.md](RUNBOOK.md).

## Pickup reminders (migration 0010)

Migration `0010_pickup_reminders` adds one column (`claim.pickup_reminded_at`). Students with an
approved claim who haven't collected the item after `PICKUP_REMINDER_DAYS` get one in-app and
email reminder. On Vercel, set `CRON_SECRET`; the cron in `vercel.json` calls the endpoint daily.
Elsewhere, run `flask --app app claims remind-pickups` once a day.

## Onboarding: the three colleges

Migration `0009_onboarding` (additive: student ID, department and year on accounts, a
`pending_registration` table, and `college.listed_on_signup`). After `flask --app app db upgrade`,
set up the colleges shown on the sign-up screen. The command is safe to re-run: an existing
college with the same slug is updated, never duplicated (on the 2.0 database, Alliance already
exists as `alliance` after `legacy adopt`).

```
flask --app app college onboard --name "Alliance University" --slug alliance \
    --domain ced.alliance.edu.in --short-name Alliance --city Bengaluru --color "#1d4ed8"
flask --app app college onboard --name "MVJ College of Engineering" --slug mvj-ce \
    --domain mvjce.edu.in --short-name MVJCE --city Bengaluru --color "#b91c1c"
flask --app app college onboard --name "Vemana Institute of Technology" --slug vemana-it \
    --domain vemanait.edu.in --short-name "Vemana IT" --city Bengaluru --color "#047857"
```

- **Logos:** cards show a monogram (AU, MCE, VIT) until you add an official logo with
  `--logo-url https://...` (only use logos you're allowed to use). The colours are placeholders too.
- **More colleges later:** add them in the platform console, then tick "Show on the public
  sign-up and sign-in screens" (or run `college onboard`).
- **Departments:** students type their department; if you add rows to the `department` table
  for a college, they appear as suggestions.
- **Sign-in:** `/login` now opens the React sign-in (`/app/signin`). Staff whose email isn't
  on the college domain, and platform admins, use `/admin_login`.
- **Rate limits:** `REGISTER_RATE_LIMIT` (default 40 per hour per IP) covers the sign-up form
  and code resends. It is higher than the code limit because a hostel or campus Wi-Fi often
  shares one IP; each email still waits 60 seconds between codes. Use Redis (`REDIS_URL`) so
  the limits hold across Vercel instances.
- **Email is required:** without working `MAIL_*` settings nobody receives a code, so nobody
  can register. Send yourself a test registration after deploying.

## Accounts and roles

| Role | Created by | Can |
|---|---|---|
| `platform_super_admin` | CLI only | Add, activate and suspend colleges; invite college admins (`/platform/`). No access to college items. |
| `college_admin` | Platform console invite or CLI | Review claims, remove listings, see private identifying details, manage collection points, use the pickup desk. |
| `campus_moderator` | CLI (`--campus` limits them to one campus) | Review claims and listings for their campus. |
| `security_staff` | CLI (`--campus` limits them to one campus) | Pickup desk (`/desk/`): hand items over after checking the claimant's code. |
| `student` | Self-registration with a verified college email | Report, search, claim. |

Invited admins set their password through **Forgot password?**, which also verifies their email.

## React frontend

The React app is built ahead of time into `static/app/` and committed, so Vercel's Python
build needs no Node step: Flask serves it at `/app/`. After changing anything in `frontend/`,
run `cd frontend && npm ci && npm run build` and commit the updated `static/app/`.
`frontend/` itself is excluded from the Vercel upload (`.vercelignore`).

Set `USE_REACT_APP=0` to make the classic server-rendered pages the default again after
sign-in (both keep working either way).

## Health check and monitoring

- `GET /healthz` returns `{"status": "ok", "database": "ok"}`, or 503 when the database is
  unreachable. Point an uptime monitor (e.g. UptimeRobot, Better Stack) at it.
- Errors go to the application log (Vercel → Logs). Sentry is planned for Phase 7.

## Running locally

```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # fill SECRET_KEY and DATABASE_URL
createdb campus_retain_dev      # DATABASE_URL=postgresql:///campus_retain_dev
flask --app app db upgrade
flask --app app run
```

Tests need two throwaway databases:

```
createdb campus_retain_test && createdb campus_retain_migtest
pytest
```

## Vercel compatibility

Works on Vercel's Python runtime for this phase. Known limits:

- **Rate limits** are per instance unless `RATELIMIT_STORAGE_URI` points at Redis. Account
  lockout is stored in the database, so it works across instances regardless.
- **Photos** go to R2 (max 3 per item, 1600 px JPEG, metadata removed). Uploads pass through
  the function, so Vercel's 4.5 MB request limit applies: about 3 phone photos of normal size.
  Larger photos get a clear error. Direct-to-R2 uploads can come with the React frontend.
- **Matching** runs inside the report request (one database query), so no background
  worker is needed. AI checks run only when a person asks for one.
- **Push notifications** are sent at the end of the request that created them (5-second
  timeout per browser), so they add a little time to that request.
- **Bundle size:** boto3, the Anthropic SDK, Sentry and the PDF/Excel libraries fit within
  Vercel's Python function limit, but watch it if you add more.
- Bundle: `tests/`, `docs/` and local files are excluded by `.vercelignore`.
