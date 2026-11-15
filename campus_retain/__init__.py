"""Campus Retain 3.0 application factory."""
import logging
import os

from flask import Flask, g, jsonify, render_template, request
from flask_wtf.csrf import CSRFError
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import load_config
from .extensions import csrf, db, limiter, migrate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Third-party origins the existing pages load from (Tailwind browser build, fonts, animate.css).
CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data: blob: https:",
    "connect-src 'self'",
    "frame-ancestors 'none'",
    "form-action 'self'",
    "base-uri 'self'",
    "object-src 'none'",
])

MAINTENANCE_ALLOWED = {"static", "health.healthz", "tags.scan", "auth.login", "auth.admin_login", "auth.logout",
                       "auth.forgot_password", "auth.verify_code", "auth.resend_code"}


def create_app(env_name=None, overrides=None):
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(ROOT, ".env"))
    except ImportError:
        pass

    app = Flask(__name__, template_folder=os.path.join(ROOT, "templates"),
                static_folder=os.path.join(ROOT, "static"))
    app.config.from_mapping(load_config(env_name, overrides))

    if os.environ.get("VERCEL") or os.environ.get("TRUST_PROXY") == "1":
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    logging.basicConfig(level=logging.INFO)

    db.init_app(app)
    migrate.init_app(app, db, directory=os.path.join(ROOT, "migrations"))
    csrf.init_app(app)
    limiter.init_app(app)

    from . import models  # noqa: F401  (register models with SQLAlchemy)
    from .blueprints import admin, api, api_v1, auth, auth_api, desk, health, media, platform, spa, student, tags
    for module in (auth, auth_api, student, admin, api, api_v1, platform, health, media, desk, spa, tags):
        app.register_blueprint(module.bp)
    csrf.exempt(health.bp)

    from .cli import register_cli
    register_cli(app)

    from . import rls
    from .security import load_current_user
    rls.register(app)
    from .services import monitoring, push
    monitoring.init_sentry(app)
    push.register(app)

    @app.before_request
    def _load_user():
        load_current_user()
        rls.capture_scope()
        rls.apply_scope()   # second isolation layer: PostgreSQL row-level security

    @app.before_request
    def _maintenance():
        if not app.config.get("MAINTENANCE_MODE") or request.endpoint in MAINTENANCE_ALLOWED:
            return None
        user = g.get("user")
        if user is not None and (user.role and (user.role.is_platform or user.has_permission("claims.review"))):
            return None
        return render_template("maintenance.html"), 503

    @app.context_processor
    def _template_globals():
        user = g.get("user")
        return {"current_user": user, "current_college": g.get("college"),
                "app_name": app.config["APP_NAME"],
                "photo_url": media.photo_url, "photo_urls": media.photo_urls}

    @app.after_request
    def _security_headers(response):
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        h.setdefault("Permissions-Policy", "camera=(self), microphone=(), geolocation=(self)")
        h.setdefault("Content-Security-Policy", CSP)
        if app.config.get("SESSION_COOKIE_SECURE"):
            h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if g.get("user") is not None and request.blueprint != "media":
            h.setdefault("Cache-Control", "no-store")
        return response

    _register_error_handlers(app)
    return app


def _register_error_handlers(app):
    messages = {
        400: "That request wasn't valid.",
        403: "You don't have access to this page.",
        404: "We couldn't find that page.",
        405: "That action isn't allowed here.",
        413: "That upload is too large.",
        429: "Too many attempts. Please wait a little and try again.",
        500: "Something went wrong on our side. Please try again.",
    }

    def respond(code, message=None):
        message = message or messages.get(code, messages[500])
        if request.path.startswith("/api/"):
            return jsonify({"error": message}), code
        return render_template("error.html", code=code, message=message), code

    @app.errorhandler(CSRFError)
    def _csrf(_e):
        return respond(400, "Your session expired or the form was out of date. Reload the page and try again.")

    for code in (400, 403, 404, 405, 413, 429):
        app.register_error_handler(code, lambda e, c=code: respond(c))

    @app.errorhandler(500)
    def _server_error(_e):
        db.session.rollback()
        return respond(500)
