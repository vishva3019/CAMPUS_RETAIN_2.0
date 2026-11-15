"""Environment-based configuration. Production fails fast when required secrets are missing."""
import os
from datetime import timedelta


class ConfigError(RuntimeError):
    pass


def _bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def normalize_database_url(url):
    """Use the psycopg 3 driver explicitly (SQLAlchemy 2.1's default for postgresql://)."""
    url = url or ""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def _database_url():
    return normalize_database_url(os.environ.get("DATABASE_URL", ""))


def ratelimit_storage_uri():
    return os.environ.get("RATELIMIT_STORAGE_URI") or os.environ.get("REDIS_URL") or "memory://"


class BaseConfig:
    APP_NAME = "Campus Retain"

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 300}

    # Sessions
    # Normal sessions end when the browser closes or after SESSION_HOURS, whichever is first.
    # Students who tick "Keep me signed in" stay signed in for REMEMBER_DAYS (staff never do).
    # Both limits are also enforced on the server (session["exp"]), not only by the cookie.
    SESSION_HOURS = int(os.environ.get("SESSION_HOURS", 8))
    REMEMBER_DAYS = int(os.environ.get("REMEMBER_DAYS", 30))
    PERMANENT_SESSION_LIFETIME = timedelta(days=REMEMBER_DAYS)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = True

    # CSRF (Flask-WTF). Tokens live as long as the session.
    WTF_CSRF_TIME_LIMIT = None
    WTF_CSRF_HEADERS = ["X-CSRFToken"]

    # Rate limiting (Flask-Limiter). memory:// is per-process; use Redis in production.
    RATELIMIT_ENABLED = True
    # REDIS_URL (e.g. Upstash rediss://...) makes limits shared across serverless instances.
    RATELIMIT_STORAGE_URI = None   # set from the environment in load_config (ratelimit_storage_uri)
    RATELIMIT_HEADERS_ENABLED = True
    LOGIN_RATE_LIMIT = "10 per minute"
    CODE_REQUEST_RATE_LIMIT = "5 per hour"
    # Sign-up form and its code resends, per IP. Higher than the code limit above because a
    # whole hostel or campus Wi-Fi often shares one IP; each email still waits
    # CODE_RESEND_SECONDS between codes.
    REGISTER_RATE_LIMIT = "40 per hour"
    PENDING_REGISTRATION_HOURS = 2
    CODE_VERIFY_RATE_LIMIT = "15 per 10 minutes"

    # Account lockout
    MAX_FAILED_LOGINS = 5
    LOCKOUT_MINUTES = 15

    # Verification codes
    CODE_TTL_MINUTES = 10
    CODE_MAX_ATTEMPTS = 5
    CODE_RESEND_SECONDS = 60
    MIN_PASSWORD_LENGTH = 8

    # Uploads
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024
    MAX_IMAGE_BYTES = 5 * 1024 * 1024
    IMAGE_MAX_DIMENSION = 1600

    MAX_PHOTOS_PER_ITEM = 3

    # Photo storage: "r2" (Cloudflare R2, S3 API), "local" (folder, development only),
    # "memory" (tests) or "database" (2.0 behaviour: compressed photo in item.image_data).
    # Defaults to r2 when R2_BUCKET is set, otherwise database.
    STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND") or ("r2" if os.environ.get("R2_BUCKET") else "database")
    R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID")
    R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID")
    R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY")
    R2_BUCKET = os.environ.get("R2_BUCKET")
    R2_ENDPOINT_URL = os.environ.get("R2_ENDPOINT_URL")   # optional; derived from R2_ACCOUNT_ID
    MEDIA_URL_TTL_SECONDS = 300                           # life of a signed photo link
    LOCAL_MEDIA_DIR = os.environ.get("LOCAL_MEDIA_DIR", os.path.join(os.getcwd(), "instance", "media"))

    # Pickup codes (sent when a claim is approved, checked by security staff)
    PICKUP_CODE_TTL_DAYS = 14
    PICKUP_CODE_MAX_ATTEMPTS = 5
    PICKUP_CODE_RESEND_SECONDS = 60
    PICKUP_REMINDER_DAYS = int(os.environ.get("PICKUP_REMINDER_DAYS", 3))
    # Vercel Cron sends "Authorization: Bearer <CRON_SECRET>" to /internal/cron/* when set.
    CRON_SECRET = os.environ.get("CRON_SECRET")

    # Pagination
    PAGE_SIZE = 24

    # Mail: "smtp" sends real email, "console" prints it, "memory" stores it (tests).
    MAIL_BACKEND = os.environ.get("MAIL_BACKEND", "smtp")
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_FROM_NAME = os.environ.get("MAIL_DEFAULT_FROM_NAME", "Campus Retain")

    # SMS (optional)
    TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
    TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
    TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER")
    SMS_DEFAULT_COUNTRY_CODE = os.environ.get("SMS_DEFAULT_COUNTRY_CODE", "+91")

    MAINTENANCE_MODE = _bool("MAINTENANCE_MODE")

    # Optional Claude features (photo-to-description, AI match check). Off without a key.
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
    AI_MODEL = os.environ.get("AI_MODEL", "claude-opus-5-5")
    AI_TIMEOUT_SECONDS = 60
    AI_RATE_LIMIT = os.environ.get("AI_RATE_LIMIT", "30 per hour")
    # Chatbot and "Search with AI", per signed-in user (works with or without an AI key).
    ASSISTANT_RATE_LIMIT = os.environ.get("ASSISTANT_RATE_LIMIT", "60 per hour")

    # Error monitoring (Sentry). Off without a DSN.
    SENTRY_DSN = os.environ.get("SENTRY_DSN")
    SENTRY_TRACES_SAMPLE_RATE = float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0"))

    # Browser push notifications (Web Push). Generate keys with: flask --app app push vapid-keys
    VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY")
    VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY")
    VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT")          # mailto:you@example.com

    # Send signed-in users to the React app (/app/) when its build exists in static/app.
    # Set USE_REACT_APP=0 to keep the classic server-rendered pages as the default.
    USE_REACT_APP = _bool("USE_REACT_APP", True)


class ProductionConfig(BaseConfig):
    ENV_NAME = "production"


class DevelopmentConfig(BaseConfig):
    ENV_NAME = "development"
    SESSION_COOKIE_SECURE = False
    MAIL_BACKEND = os.environ.get("MAIL_BACKEND", "console")
    STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND") or ("r2" if os.environ.get("R2_BUCKET") else "local")


class TestConfig(BaseConfig):
    ENV_NAME = "test"
    TESTING = True
    SESSION_COOKIE_SECURE = False
    MAIL_BACKEND = "memory"
    RATELIMIT_ENABLED = False
    RATELIMIT_STORAGE_URI = "memory://"
    SECRET_KEY = "test-secret-key-not-for-production-0123456789"
    TWILIO_ACCOUNT_SID = None
    TWILIO_AUTH_TOKEN = None
    TWILIO_PHONE_NUMBER = None
    MAINTENANCE_MODE = False
    STORAGE_BACKEND = "memory"
    USE_REACT_APP = False
    ANTHROPIC_API_KEY = None
    SENTRY_DSN = None
    VAPID_PUBLIC_KEY = None
    VAPID_PRIVATE_KEY = None


STORAGE_BACKENDS = ("r2", "local", "memory", "database")

CONFIGS = {
    "production": ProductionConfig,
    "development": DevelopmentConfig,
    "test": TestConfig,
}


def load_config(env_name=None, overrides=None):
    """Return a dict of settings for the chosen environment, validated."""
    env_name = env_name or os.environ.get("APP_ENV") or ("production" if os.environ.get("VERCEL") else "development")
    if env_name not in CONFIGS:
        raise ConfigError(f"Unknown APP_ENV '{env_name}'. Use one of: {', '.join(CONFIGS)}")

    cls = CONFIGS[env_name]
    settings = {k: getattr(cls, k) for k in dir(cls) if k.isupper()}
    if settings.get("RATELIMIT_STORAGE_URI") is None:
        settings["RATELIMIT_STORAGE_URI"] = ratelimit_storage_uri()

    if env_name != "test":
        settings["SECRET_KEY"] = os.environ.get("SECRET_KEY")
        settings["SQLALCHEMY_DATABASE_URI"] = _database_url()
    else:
        settings["SQLALCHEMY_DATABASE_URI"] = os.environ.get("TEST_DATABASE_URL", "sqlite://")

    if overrides:
        settings.update(overrides)
    settings["SQLALCHEMY_DATABASE_URI"] = normalize_database_url(settings.get("SQLALCHEMY_DATABASE_URI"))

    missing = [k for k in ("SECRET_KEY", "SQLALCHEMY_DATABASE_URI") if not settings.get(k)]
    if missing:
        names = {"SECRET_KEY": "SECRET_KEY", "SQLALCHEMY_DATABASE_URI": "DATABASE_URL"}
        raise ConfigError(
            "Missing required configuration: " + ", ".join(names[m] for m in missing)
            + ". See .env.example."
        )
    if env_name == "production" and len(settings["SECRET_KEY"]) < 32:
        raise ConfigError("SECRET_KEY must be at least 32 characters in production.")
    backend = settings.get("STORAGE_BACKEND")
    if backend not in STORAGE_BACKENDS:
        raise ConfigError(f"Unknown STORAGE_BACKEND '{backend}'. Use one of: {', '.join(STORAGE_BACKENDS)}")
    if backend == "r2":
        need = [k for k in ("R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET") if not settings.get(k)]
        if not settings.get("R2_ENDPOINT_URL") and not settings.get("R2_ACCOUNT_ID"):
            need.append("R2_ACCOUNT_ID")
        if need:
            raise ConfigError("STORAGE_BACKEND=r2 needs: " + ", ".join(need) + ". See .env.example.")
    if env_name == "production" and backend in ("local", "memory"):
        raise ConfigError("STORAGE_BACKEND local/memory can't be used in production (Vercel's disk is not persistent).")
    if settings["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        # SQLite has no connection pool options
        settings["SQLALCHEMY_ENGINE_OPTIONS"] = {}

    settings["ENV_NAME"] = env_name
    return settings
