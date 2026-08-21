"""Public, non-application routes: crawler files and health checks.

These are deliberately exempt from the login wall and from maintenance mode so
that uptime monitoring keeps working during an upgrade.
"""

from __future__ import annotations

from flask import Blueprint, Response, current_app, url_for

from app.extensions import db

bp = Blueprint("site", __name__)


@bp.route("/robots.txt")
def robots() -> Response:
    """Keep the register out of search results.

    Every meaningful page sits behind a login, and the item listings describe
    other people's lost property, so there is nothing here that should be
    indexed. Only the sign-in pages are left crawlable.
    """
    body = "\n".join(
        [
            "User-agent: *",
            "Disallow: /api/",
            "Disallow: /admin",
            "Disallow: /verify",
            "Disallow: /reset-password",
            "Disallow: /forgot-password",
            "Allow: /login",
            "Allow: /signup",
            "Disallow: /",
            "",
            f"Sitemap: {current_app.config['SITE_URL'].rstrip('/')}/sitemap.xml",
            "",
        ]
    )
    return Response(body, mimetype="text/plain")


@bp.route("/sitemap.xml")
def sitemap() -> Response:
    """Minimal sitemap covering only the publicly reachable entry points."""
    base = current_app.config["SITE_URL"].rstrip("/")
    paths = [url_for("auth.login"), url_for("auth.signup")]
    urls = "".join(f"<url><loc>{base}{path}</loc></url>" for path in paths)
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{urls}"
        "</urlset>"
    )
    return Response(body, mimetype="application/xml")


@bp.route("/healthz")
def healthz():
    """Liveness probe that also confirms the database is reachable."""
    try:
        db.session.execute(db.text("SELECT 1"))
    except Exception:
        current_app.logger.exception("Health check failed")
        return {"status": "error", "database": "unreachable"}, 503
    return {"status": "ok", "database": "ok"}
