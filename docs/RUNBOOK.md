# Campus Retain runbook: backups, restores and incidents

## What holds data

| Store | What | Backed up by |
|---|---|---|
| Neon PostgreSQL | everything except photos | Neon point-in-time restore (history window depends on your Neon plan) + your own dumps |
| Cloudflare R2 bucket | item photos (`colleges/<id>/items/...`) | not versioned by default: see below |
| Vercel env settings | secrets | keep a copy in a password manager |

## Routine backups

- **Daily (automatic):** Neon keeps a restore window. Check the length on your plan
  (Neon console → Project → Settings → Storage / History retention) and set it to at least 7 days.
- **Weekly (manual or scheduled, 5 minutes):**
  ```
  pg_dump "$OWNER_DATABASE_URL" --format=custom --file=campus-retain-$(date +%F).dump
  ```
  Keep the last 8 somewhere other than Neon (encrypted drive or a private bucket).
- **Before every migration or bulk change:** create a Neon branch (instant copy) named
  `backup-YYYY-MM-DD` and keep it until the change is verified.
- **Photos:** R2 has no automatic versioning. To keep a copy, sync the bucket with
  `rclone sync r2:campus-retain-photos ./photos-backup` monthly, or turn on R2's
  bucket lock / lifecycle rules if your plan has them.

## Restore drill (do it once a term)

1. Neon console → Branches → create a branch from a point in time (e.g. yesterday 09:00).
2. Point a local copy of the app at that branch (`DATABASE_URL=...` in `.env`), run
   `flask --app app run` and sign in as a college admin. Check items, claims and the activity log.
3. Note how long it took. Delete the branch.

## Restoring production for real

1. Turn on `MAINTENANCE_MODE=1` on Vercel and redeploy (staff can still sign in).
2. In Neon, restore the main branch to the chosen time (or promote a backup branch).
   Neon keeps the pre-restore state as a branch, so this can be undone.
3. Run `flask --app app db current` against it; if it is behind, run `flask --app app db upgrade`.
4. Turn maintenance mode off and redeploy. Write down what was lost between the restore
   point and the incident, and tell affected colleges.

## Incidents

- **Suspected data leak between colleges:** turn on maintenance mode, check the activity
  log (`/app/platform/activity`) for `network.*`, `items.exported` and `analytics.exported`
  entries, and confirm the app connects with the restricted `campus_retain_app` role
  (`SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user;` must be false).
- **Leaked secret:** rotate it at the provider (Neon password, R2 token, Anthropic key,
  VAPID keys, `SECRET_KEY`), update Vercel, redeploy. Rotating `SECRET_KEY` signs everyone out.
- **Errors spike:** check Sentry, then Vercel → Logs. `/healthz` returns 503 when the
  database is unreachable.
- **Spam on a QR tag page:** the page is rate-limited per IP; the owner can turn the tag off
  under My QR tags.
