# Campus Retain 3.0

**One platform. Multiple colleges. One connected campus community.**

Campus Retain is a lost-and-found platform for colleges. Each college gets its own private
space (its students, staff, items, claims and settings), and students sign in with their
verified college email.

> Status: **all 7 phases built** (not yet deployed). See [docs/ROADMAP.md](docs/ROADMAP.md),
> [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) and [docs/RUNBOOK.md](docs/RUNBOOK.md). See [docs/ROADMAP.md](docs/ROADMAP.md)
> for the audit of 2.0 and the plan. The live 2.0 site (campus-retain-2-0.vercel.app) is
> unchanged until this version is deployed.

## What works today

- **Onboarding:** an animated welcome page at `/`, then pick your college, enter your details
  in three short steps, confirm a 6-digit code sent to your college email, and you're in. Each
  college accepts only its own email domain (checked again on the server), the account exists
  only after the code is confirmed, and returning students go straight to their dashboard.

- **Colleges:** many colleges on one deployment, matched by email domain (subdomains included),
  each with its own branded sign-in page at `/c/<slug>/login`. New colleges start as *pending*
  until a platform admin activates them. Suspending a college signs its users out.
- **Accounts:** registration only after a 6-digit email code. Codes are hashed, expire in
  10 minutes and stop working after 5 wrong tries. Accounts lock for 15 minutes after 5 wrong
  passwords. A password reset signs out every other session.
- **Roles:** Platform Super Admin, College Admin, Campus Moderator, Security Staff and Student,
  with permissions checked on the server for every page and API call.
- **Isolation:** every query is limited to the signed-in user's college (and campus, for
  moderators). Another college's items return 404, even when their ids are guessed.
- **Lost and found:** report found items with a description, date and photo (validated,
  resized and stripped of metadata). Search and pagination. Claims with ownership proof. One
  active claim per item, enforced by the database. Approve or reject with remarks. Every claim
  keeps its own outcome, so history is never overwritten. Removing a listing hides it but
  keeps the record.
- **Accountability:** audit log of sign-ins, registrations, resets, reports, claims, reviews
  and college changes. In-app notification records plus email (and optional SMS).
- **Security:** CSRF on every form and API call, rate limits, security headers (CSP, frame
  denial, nosniff, HSTS on HTTPS), secure session cookies with an 8-hour lifetime, safe error
  pages, and no public setup or test endpoints.
- **Photos:** up to 3 per item, compressed, stored in a private Cloudflare R2 bucket and shown
  only to signed-in members of the same college (short-lived signed links).
- **Collection points:** college admins list where items are handed in (`/admin/collection-points`);
  approved claimants are told exactly where to go.
- **Pickup codes:** approving a claim emails a one-time 6-digit code. Security staff check it at
  the pickup desk (`/desk/`) before handing the item over; 5 wrong tries lock it until the
  student sends a new code. Every handover is recorded.
- **Lost items:** students post what they lost; anyone who finds it taps *I found this*, and the
  owner gets an email. *My activity* (`/me`) shows claims, reports and notifications.
- **React app** (`/app/`): after signing in, students, staff and platform admins land in a
  React + TypeScript app with light and dark themes, a phone tab bar, a notification centre and
  CSV export for admins. Sign-in pages stay server-rendered, and the classic pages still work.
- **Analytics** from real data with Excel/PDF/CSV exports, and an activity log of every
  sign-in, decision, handover and export.
- **Matching:** found items are matched to lost reports by text similarity and owners are
  alerted; duplicate reports are flagged before posting; search tolerates typos; reviewers
  see warnings on suspicious claims. Optional Claude features suggest descriptions from a
  photo and give a second opinion on a match (needs an Anthropic API key).
- **Network and events:** opt-in inter-college search with redacted listings, event portals
  with QR posters, QR stickers for belongings (finders message the owner anonymously), and a
  map of approximate found locations.
- **Plans and hardening:** Free / Standard / Premium plans assigned by the platform admin,
  PostgreSQL row-level security, Redis rate limits, Sentry, browser push notifications.
- **Platform console** (`/platform/`): add, activate and suspend colleges; invite college admins.
- **Health check:** `GET /healthz`.

## Project layout

```
app.py                      entry point (Vercel / flask --app app)
campus_retain/
  __init__.py               app factory, security headers, error pages
  config.py                 environment config; production fails fast on missing secrets
  models.py                 College, Campus, Department, Role, Permission, User, Item,
                            ItemImage, Claim, Notification, CollectionPoint, Event,
                            AuditLog, Subscription, PlatformSetting, EmailCode
  security.py               roles, permission decorators, tenant-scoped queries
  services/                 claims workflow, codes, email/SMS, images, audit
  blueprints/               auth, student, admin, api, platform, health
  cli.py                    flask college | user | rbac | legacy commands
migrations/                 Alembic; upgrades a 2.0 database in place
templates/, static/         pages (React frontend arrives in Phase 3)
frontend/                   React app (Vite + TypeScript + Tailwind); builds into static/app
tests/                      pytest suite, runs on PostgreSQL
docs/                       ROADMAP.md, DEPLOYMENT.md
```

## Run it locally

```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                 # set SECRET_KEY and DATABASE_URL
flask --app app db upgrade
flask --app app user create --email you@example.com --role platform_super_admin
flask --app app run
```

Then sign in, open `/platform/`, add a college with your email domain and activate it.

The React app is already built into `static/app`. To work on it:

```
cd frontend && npm ci
npm run dev          # http://localhost:5173/app/ (proxies the API to Flask on :5055)
npm test             # unit tests
npm run build        # typecheck + rebuild static/app (commit the result)
```

Run the tests (two throwaway PostgreSQL databases):

```
createdb campus_retain_test && createdb campus_retain_migtest
pytest
```

Deploying, and upgrading the existing 2.0 database: see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Author

VISHVANTH — B.Tech Computer Science and Engineering · GitHub: https://github.com/vishva3019

## License

This repository is reserved strictly for academic evaluations and educational campus implementations.
