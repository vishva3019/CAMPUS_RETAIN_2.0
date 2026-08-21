"""Application factory.

Using a factory rather than a module-level ``app`` object is what makes the
test suite possible: each test builds an isolated application with its own
configuration and database, instead of importing a singleton that has already
read the environment and connected to production.
"""

from __future__ import annotations

import logging
from pathlib import Path

from flask import Flask, jsonify, render_template, request, session
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

from app.config import resolve_config
from app.extensions import csrf, db, migrate
from app.services.storage import build_storage

# Endpoints reachable while maintenance mode is on. Health checks stay up so
# monitoring does not page during a planned upgrade, and admins can still work.
MAINTENANCE_ALLOWED_ENDPOINTS = frozenset(
    {
        "static",
        "site.healthz",
        "site.robots",
        "admin.login",
        "admin.dashboard",
        "admin.logout",
    }
)


def create_app(config_name: str | None = None) -> Flask:
    # Load .env before reading configuration so local development picks it up.
    _load_dotenv()

    app = Flask(__name__, instance_relative_config=True)

    config_class = resolve_config(config_name)
    app.config.from_object(config_class)
    # Raises ConfigError on a misconfigured production deploy, by design: a
    # loud failure at boot is far better than silently running with a
    # predictable session key.
    config_class.validate()

    _configure_logging(app)

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    app.extensions["campusretain_storage"] = build_storage(app)

    _register_blueprints(app)
    _register_request_hooks(app)
    _register_error_handlers(app)
    _register_template_context(app)
    _register_cli(app)

    return app


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - python-dotenv is a hard dependency
        return
    env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(env_path, override=False)


def _configure_logging(app: Flask) -> None:
    """Log to stdout, which is what Vercel captures."""
    level = logging.DEBUG if app.debug else logging.INFO
    app.logger.setLevel(level)
    if not app.logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("[%(asctime)s] %(levelname)s in %(module)s: %(message)s")
        )
        app.logger.addHandler(handler)


def _register_blueprints(app: Flask) -> None:
    from app.blueprints import admin, api, auth, items, site

    app.register_blueprint(site.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(items.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(api.bp)


def _register_request_hooks(app: Flask) -> None:
    from app.services import ratelimit

    @app.before_request
    def enforce_maintenance():
        if not app.config.get("MAINTENANCE_MODE"):
            return None
        if request.endpoint in MAINTENANCE_ALLOWED_ENDPOINTS:
            return None
        if session.get("is_admin") is True:
            return None
        # Previously this matched endpoint names with a substring test against a
        # list that included "logout" and "static", so any endpoint *containing*
        # one of those words was exempt. Exact matching only.
        return render_template("errors/maintenance.html"), 503

    @app.before_request
    def throttle_sensitive_endpoints():
        """Coarse abuse limits on the endpoints that cost money or send mail."""
        if request.method != "POST":
            return None

        rules = {
            "auth.login": ("login", 10, 300),
            "auth.signup": ("signup", 5, 900),
            "auth.forgot_password": ("forgot", 5, 900),
            "auth.resend_verification": ("resend", 5, 900),
            "auth.reset_password": ("reset", 10, 900),
            "admin.login": ("admin-login", 10, 900),
            "api.report_item": ("report", 20, 3600),
            "api.create_claim": ("claim", 20, 3600),
        }

        rule = rules.get(request.endpoint or "")
        if rule is None:
            return None

        bucket, limit, window = rule
        allowed, retry_after = ratelimit.check(bucket, limit, window)
        if allowed:
            return None

        if (request.path or "").startswith("/api/"):
            response = jsonify(
                {
                    "ok": False,
                    "error": "Too many requests. Please wait a moment "
                    "and try again.",
                }
            )
            response.status_code = 429
        else:
            response = app.make_response(
                (render_template("errors/429.html", retry_after=retry_after), 429)
            )
        response.headers["Retry-After"] = str(retry_after)
        return response

    @app.after_request
    def set_security_headers(response):
        """Baseline hardening headers, including a strict Content-Security-Policy.

        The policy can afford to be strict because the front end ships no
        third-party code and no inline scripts: stylesheets and scripts are
        served from ``/static``, and page data reaches JavaScript through
        ``<script type="application/json">`` data islands, which the CSP does
        not need to whitelist because they are never executed.

        The previous front end pulled in the Tailwind browser build, animate.css
        and Google Fonts from three separate CDNs and compiled its stylesheet in
        the browser on every page load, which no policy this tight would permit.
        """
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        if not app.debug:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        response.headers.setdefault(
            "Content-Security-Policy",
            "; ".join(
                [
                    "default-src 'self'",
                    # Cloudinary serves item photographs; data: covers the
                    # inline SVG placeholder for items with no image.
                    "img-src 'self' data: https://res.cloudinary.com",
                    "script-src 'self'",
                    "style-src 'self'",
                    "font-src 'self'",
                    "connect-src 'self'",
                    "object-src 'none'",
                    "frame-ancestors 'none'",
                    "base-uri 'self'",
                    "form-action 'self'",
                ]
            ),
        )
        return response


def _register_error_handlers(app: Flask) -> None:
    def wants_json() -> bool:
        return (request.path or "").startswith("/api/")

    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        app.logger.warning("CSRF validation failed: %s", error.description)
        if wants_json():
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "Your session expired. Please reload the page "
                        "and try again.",
                    }
                ),
                400,
            )
        return render_template("errors/csrf.html"), 400

    @app.errorhandler(RequestEntityTooLarge)
    def handle_too_large(_error):
        limit_mb = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
        message = f"That file is too large. The maximum size is {limit_mb} MB."
        if wants_json():
            return jsonify({"ok": False, "error": message}), 413
        return render_template("errors/generic.html", message=message), 413

    @app.errorhandler(404)
    def handle_not_found(_error):
        if wants_json():
            return jsonify({"ok": False, "error": "Not found."}), 404
        return render_template("errors/404.html"), 404

    @app.errorhandler(Exception)
    def handle_unexpected(error):
        """Catch-all that logs the detail and returns a generic message.

        The old code returned ``str(e)`` to the browser, exposing database
        schema, driver internals and file paths. The traceback now goes to the
        server log where it belongs.
        """
        if isinstance(error, HTTPException):
            return error

        db.session.rollback()
        app.logger.exception("Unhandled exception")

        if wants_json():
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "Something went wrong on our side. "
                        "Please try again.",
                    }
                ),
                500,
            )
        return render_template("errors/500.html"), 500


def _register_template_context(app: Flask) -> None:
    @app.context_processor
    def inject_globals():
        from app.security import current_user_email, is_admin

        return {
            "site_name": app.config["SITE_NAME"],
            "support_location": app.config["SUPPORT_LOCATION"],
            "current_user_email": current_user_email(),
            "viewer_is_admin": is_admin(),
        }


def _register_cli(app: Flask) -> None:
    """Management commands.

    These replace the previous ``/init-db``, ``/test-email`` and ``/test-sms``
    HTTP routes, all of which were reachable by anyone on the internet. Hitting
    ``/test-sms`` sent a message to a phone number hardcoded in the source, so
    anyone could have looped it to burn through the Twilio balance. A CLI
    command requires shell access, so the capability is no longer public.
    """
    import click

    @app.cli.command("init-db")
    def init_db_command() -> None:
        """Create tables directly. Prefer 'flask db upgrade' once migrations exist."""
        db.create_all()
        click.echo("Database tables created.")

    @app.cli.command("create-admin-hash")
    @click.argument("password")
    def create_admin_hash(password: str) -> None:
        """Print a hash to paste into ADMIN_PASSWORD_HASH."""
        from werkzeug.security import generate_password_hash

        click.echo(generate_password_hash(password))

    @app.cli.command("send-test-email")
    @click.argument("recipient")
    def send_test_email(recipient: str) -> None:
        """Verify SMTP configuration."""
        from app.services.mail import send_email

        ok = send_email(
            recipient,
            f"{app.config['SITE_NAME']} test email",
            "SMTP is configured correctly.",
        )
        click.echo("Sent." if ok else "Failed. Check the log output above.")

    @app.cli.command("prune-rate-limits")
    def prune_rate_limits() -> None:
        """Delete expired rate-limit rows."""
        from app.services import ratelimit

        click.echo(f"Deleted {ratelimit.prune()} expired row(s).")
