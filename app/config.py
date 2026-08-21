"""Configuration objects for CampusRetain.

Configuration is environment-driven. The guiding rule is **fail fast**: in
production the application refuses to start rather than boot with an insecure
default. The old single-file app fell back to a hardcoded ``SECRET_KEY``, which
meant that if the environment variable were ever missing on Vercel, anyone could
forge a signed session cookie containing ``is_admin: True``. That class of bug
is now impossible.
"""

from __future__ import annotations

import os
from datetime import timedelta


class ConfigError(RuntimeError):
    """Raised at startup when required configuration is missing or unsafe."""


# Placeholder used by the development config and by .env.example. Treated as
# "unset" so a copied-and-not-edited .env cannot reach production.
INSECURE_SECRET_PLACEHOLDER = "change-me-generate-a-real-random-value"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc


def _normalise_database_url(url: str) -> str:
    """Make legacy Postgres URLs usable by SQLAlchemy 2.x.

    Neon and Heroku hand out ``postgres://`` URLs; SQLAlchemy 2 only registers
    the ``postgresql://`` dialect name.
    """
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def _hash_test_password(raw: str) -> str:
    """Hash a throwaway test password cheaply.

    Imported lazily so that a production boot never pays for it.
    """
    from werkzeug.security import generate_password_hash

    return generate_password_hash(raw, method="pbkdf2:sha256:1")


class BaseConfig:
    """Settings shared by every environment."""

    # ---- Core -----------------------------------------------------------
    SECRET_KEY = os.environ.get("SECRET_KEY")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Recycle pooled connections well before a serverless-friendly Postgres
    # (Neon) drops them, and check liveness before handing one out.
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }

    # ---- Uploads --------------------------------------------------------
    # Vercel rejects request bodies larger than ~4.5 MB at the platform edge,
    # so the previous 16 MB limit could never actually be reached: uploads
    # between 4.5 and 16 MB failed with an opaque platform error instead of a
    # friendly message. Cap below the platform limit and reject cleanly.
    MAX_CONTENT_LENGTH = 4 * 1024 * 1024
    ALLOWED_IMAGE_EXTENSIONS = frozenset({"png", "jpg", "jpeg", "gif", "webp"})

    # ---- Session cookies ------------------------------------------------
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = True
    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)
    SESSION_REFRESH_EACH_REQUEST = True

    # ---- CSRF -----------------------------------------------------------
    WTF_CSRF_TIME_LIMIT = 60 * 60 * 8  # seconds; outlive a long browsing session

    # ---- Access control -------------------------------------------------
    ALLOWED_EMAIL_DOMAIN = os.environ.get(
        "ALLOWED_EMAIL_DOMAIN", "ced.alliance.edu.in"
    ).strip().lower().lstrip("@")

    ADMIN_EMAIL = (os.environ.get("ADMIN_EMAIL") or "").strip().lower()
    ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH") or ""

    MAINTENANCE_MODE = _env_bool("MAINTENANCE_MODE", False)

    # ---- Credential policy ----------------------------------------------
    MIN_PASSWORD_LENGTH = 10
    MAX_FAILED_LOGINS = 5
    LOGIN_LOCKOUT_MINUTES = 15

    OTP_TTL_MINUTES = 10
    OTP_MAX_ATTEMPTS = 5
    # Minimum gap between OTP emails to one account, to stop an attacker using
    # the endpoint to flood a student's inbox or burn the daily SMTP quota.
    OTP_RESEND_COOLDOWN_SECONDS = 60

    # ---- Mail -----------------------------------------------------------
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = _env_int("MAIL_PORT", 587)
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_FROM_NAME = os.environ.get("MAIL_FROM_NAME", "CampusRetain Portal")
    MAIL_TIMEOUT_SECONDS = 10

    # ---- Storage --------------------------------------------------------
    CLOUDINARY_URL = os.environ.get("CLOUDINARY_URL") or ""
    CLOUDINARY_FOLDER = os.environ.get("CLOUDINARY_FOLDER", "campusretain/items")

    # ---- SMS ------------------------------------------------------------
    TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
    TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
    TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER")
    SMS_DEFAULT_COUNTRY_CODE = os.environ.get("SMS_DEFAULT_COUNTRY_CODE", "+91")

    # ---- Presentation ---------------------------------------------------
    ITEMS_PER_PAGE = 12
    ITEM_CATEGORIES = (
        "Electronics",
        "Accessories",
        "Books",
        "Clothing",
        "ID & Cards",
        "Keys",
        "Water Bottles",
        "Other",
    )
    SITE_NAME = "CampusRetain"
    SITE_URL = os.environ.get("SITE_URL", "https://campusretain.in")
    SUPPORT_LOCATION = os.environ.get("SUPPORT_LOCATION", "DOSS office")

    @classmethod
    def validate(cls) -> None:
        """Hook for per-environment startup checks."""


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    # Allow http://localhost during development; secure cookies are not sent
    # over plain HTTP and would silently break local login.
    SESSION_COOKIE_SECURE = False
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-only-insecure-key"
    SQLALCHEMY_DATABASE_URI = _normalise_database_url(
        os.environ.get("DATABASE_URL") or "sqlite:///campusretain.db"
    )


# Credentials used only by the test suite. Declared here rather than in a test
# fixture so that ``TestingConfig`` is self-consistent: importing it gives you a
# config that can actually authenticate an admin.
TEST_ADMIN_EMAIL = "admin@ced.alliance.edu.in"
TEST_ADMIN_PASSWORD = "admin-test-password"


class TestingConfig(BaseConfig):
    TESTING = True
    DEBUG = False
    SESSION_COOKIE_SECURE = False
    SECRET_KEY = "testing-key-not-used-in-production"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    # Disabled wholesale in tests so each test does not have to scrape a token
    # out of the HTML; dedicated tests re-enable it to prove it is wired up.
    WTF_CSRF_ENABLED = False
    MAIL_USERNAME = None
    MAIL_PASSWORD = None
    CLOUDINARY_URL = ""
    ADMIN_EMAIL = TEST_ADMIN_EMAIL
    # Hashed at import time so no real credential is ever committed. The
    # deliberately low iteration count keeps the test suite fast; it would be
    # indefensible anywhere else, which is why it appears only here.
    ADMIN_PASSWORD_HASH = _hash_test_password(TEST_ADMIN_PASSWORD)
    OTP_RESEND_COOLDOWN_SECONDS = 0


class ProductionConfig(BaseConfig):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = _normalise_database_url(
        os.environ.get("DATABASE_URL") or ""
    )

    @classmethod
    def validate(cls) -> None:
        missing: list[str] = []

        if not cls.SECRET_KEY or cls.SECRET_KEY == INSECURE_SECRET_PLACEHOLDER:
            missing.append("SECRET_KEY")
        elif len(cls.SECRET_KEY) < 32:
            raise ConfigError(
                "SECRET_KEY is too short to be safe (need >= 32 characters). "
                "Generate one with: "
                'python -c "import secrets; print(secrets.token_urlsafe(64))"'
            )

        if not cls.SQLALCHEMY_DATABASE_URI:
            missing.append("DATABASE_URL")

        if not cls.ADMIN_EMAIL:
            missing.append("ADMIN_EMAIL")

        if not cls.ADMIN_PASSWORD_HASH:
            missing.append("ADMIN_PASSWORD_HASH")

        if missing:
            raise ConfigError(
                "Refusing to start in production without: "
                + ", ".join(missing)
                + ". Set these in the Vercel project settings. "
                "See .env.example for how to generate each value."
            )

        # A plaintext admin password in the hash slot would silently never match,
        # locking the owner out of their own dashboard. Catch the mistake loudly.
        if not cls.ADMIN_PASSWORD_HASH.startswith(
            ("pbkdf2:", "scrypt:", "argon2:")
        ):
            raise ConfigError(
                "ADMIN_PASSWORD_HASH does not look like a Werkzeug password "
                "hash. It must be the *hash*, not the plaintext password. "
                "Generate it with: python -c \"from werkzeug.security import "
                "generate_password_hash as g; print(g('your-password'))\""
            )


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def resolve_config(name: str | None = None) -> type[BaseConfig]:
    """Pick a config class from ``FLASK_ENV`` (or an explicit name)."""
    key = (name or os.environ.get("FLASK_ENV") or "development").strip().lower()
    if key not in CONFIG_MAP:
        raise ConfigError(
            f"Unknown environment {key!r}. Expected one of: "
            + ", ".join(sorted(CONFIG_MAP))
        )
    return CONFIG_MAP[key]
