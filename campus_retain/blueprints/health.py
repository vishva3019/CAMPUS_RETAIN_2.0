from flask import Blueprint, current_app, jsonify
from sqlalchemy import text

from ..extensions import db, limiter

bp = Blueprint("health", __name__)


@bp.route("/healthz")
@limiter.exempt
def healthz():
    try:
        db.session.execute(text("SELECT 1"))
        return jsonify({"status": "ok", "database": "ok"})
    except Exception:
        current_app.logger.exception("Health check: database unreachable")
        return jsonify({"status": "degraded", "database": "unreachable"}), 503


@bp.route("/internal/cron/pickup-reminders", methods=["GET", "POST"])
def cron_pickup_reminders():
    """Daily job (Vercel Cron). Needs "Authorization: Bearer <CRON_SECRET>"; disabled when
    CRON_SECRET isn't set."""
    import hmac

    from flask import abort, current_app, jsonify, request

    from ..services.claims import send_pickup_reminders
    secret = current_app.config.get("CRON_SECRET")
    given = request.headers.get("Authorization", "")
    if not secret or not hmac.compare_digest(given, f"Bearer {secret}"):
        abort(404)
    return jsonify({"status": "ok", "reminders_sent": send_pickup_reminders()})
