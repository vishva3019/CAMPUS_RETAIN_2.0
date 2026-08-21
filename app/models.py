"""Database models.

Two notes on conventions used throughout:

**Datetimes are naive UTC.** ``datetime.utcnow()`` is deprecated from Python
3.12, but the obvious replacement (``datetime.now(timezone.utc)``) returns an
*aware* datetime, and SQLite hands aware values back as naive ones. Mixing the
two raises ``TypeError`` on comparison, and it would do so only on SQLite, i.e.
locally and in tests but not on Postgres. To sidestep that entirely, every
timestamp is stored as naive UTC via :func:`utcnow`.

**Secrets are never stored in recoverable form.** Passwords and one-time codes
are hashed. In particular, OTPs live in this table rather than in the Flask
session -- see :class:`VerificationToken`.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db


def utcnow() -> datetime:
    """Current UTC time as a naive datetime (see module docstring)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ItemStatus:
    """Lifecycle of a found item."""

    AVAILABLE = "Available"
    PENDING = "Pending"
    CLAIMED = "Claimed"
    ALL = (AVAILABLE, PENDING, CLAIMED)


class ClaimStatus:
    PENDING = "Pending"
    APPROVED = "Approved"
    REJECTED = "Rejected"


class TokenPurpose:
    VERIFY_EMAIL = "verify_email"
    RESET_PASSWORD = "reset_password"
    ALL = (VERIFY_EMAIL, RESET_PASSWORD)


class User(db.Model):
    """A student account, keyed on their organisation email address."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    # An account only becomes usable once the owner proves they can read email
    # at that address. Previously any visitor could create an account for any
    # address on the allowed domain, including another student's or a staff
    # member's, simply by typing it into the login form.
    is_verified = db.Column(db.Boolean, nullable=False, default=False)

    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    last_login_at = db.Column(db.DateTime, nullable=True)

    # Brute-force throttling. Held in the database rather than in memory
    # because every Vercel request may run in a fresh process, so an
    # in-process counter would reset constantly and protect nothing.
    failed_logins = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)

    tokens = db.relationship(
        "VerificationToken",
        back_populates="user",
        lazy=True,
        cascade="all, delete-orphan",
    )

    # ---- Password handling ----------------------------------------------

    def set_password(self, raw_password: str) -> None:
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        """Verify a password.

        Unlike the previous implementation this never falls back to comparing
        plaintext. That fallback (``except: valid = user.password == password``)
        meant an unparseable hash silently downgraded the account to plaintext
        authentication.
        """
        if not self.password_hash:
            return False
        try:
            return check_password_hash(self.password_hash, raw_password)
        except (ValueError, TypeError):
            # Malformed or unrecognised hash: treat as a failed login, never
            # as a reason to compare plaintext.
            return False

    # ---- Lockout ---------------------------------------------------------

    @property
    def is_locked(self) -> bool:
        return self.locked_until is not None and self.locked_until > utcnow()

    def lockout_remaining_seconds(self) -> int:
        if not self.is_locked:
            return 0
        return max(0, int((self.locked_until - utcnow()).total_seconds()))

    def register_failed_login(self, max_attempts: int, lockout_minutes: int) -> None:
        self.failed_logins = (self.failed_logins or 0) + 1
        if self.failed_logins >= max_attempts:
            self.locked_until = utcnow() + timedelta(minutes=lockout_minutes)
            self.failed_logins = 0

    def register_successful_login(self) -> None:
        self.failed_logins = 0
        self.locked_until = None
        self.last_login_at = utcnow()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User {self.email}>"


class VerificationToken(db.Model):
    """A short-lived one-time code for email verification or password reset.

    Why this table exists at all: the previous implementation stored the reset
    OTP in the Flask session as ``session["reset_otp"]``, alongside
    ``session["reset_email"]``. Flask's default session cookie is *signed but
    not encrypted*, so its contents are readable by whoever holds the cookie.
    An attacker could therefore POST any victim's address to the
    forgot-password endpoint, read the emailed OTP straight out of their own
    cookie, and reset that victim's password -- a full account takeover with no
    access to the victim's inbox.

    Storing the code server-side, hashed, closes that hole. The client now
    holds only an opaque token id.
    """

    __tablename__ = "verification_tokens"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    purpose = db.Column(db.String(32), nullable=False, index=True)
    code_hash = db.Column(db.String(255), nullable=False)

    expires_at = db.Column(db.DateTime, nullable=False)
    consumed_at = db.Column(db.DateTime, nullable=True)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    user = db.relationship("User", back_populates="tokens")

    # ---- Issuing ---------------------------------------------------------

    @staticmethod
    def generate_code() -> str:
        """A 6-digit code from a cryptographically secure source.

        ``random.randint`` -- used previously -- is a Mersenne Twister and is
        not suitable for security tokens.
        """
        return f"{secrets.randbelow(1_000_000):06d}"

    @classmethod
    def issue(
        cls, user: User, purpose: str, ttl_minutes: int
    ) -> tuple["VerificationToken", str]:
        """Create a token, invalidating any outstanding ones for that purpose.

        Returns the token and the plaintext code. The plaintext is returned
        once, for emailing, and never persisted.
        """
        cls.query.filter_by(
            user_id=user.id, purpose=purpose, consumed_at=None
        ).update({"consumed_at": utcnow()}, synchronize_session=False)

        code = cls.generate_code()
        token = cls(
            user_id=user.id,
            purpose=purpose,
            code_hash=generate_password_hash(code),
            expires_at=utcnow() + timedelta(minutes=ttl_minutes),
        )
        db.session.add(token)
        return token, code

    @classmethod
    def latest_for(cls, user: User, purpose: str) -> "VerificationToken | None":
        return (
            cls.query.filter_by(user_id=user.id, purpose=purpose, consumed_at=None)
            .order_by(cls.created_at.desc())
            .first()
        )

    # ---- Redeeming -------------------------------------------------------

    @property
    def is_expired(self) -> bool:
        return utcnow() > self.expires_at

    @property
    def is_consumed(self) -> bool:
        return self.consumed_at is not None

    def verify(self, code: str, max_attempts: int) -> tuple[bool, str | None]:
        """Check a submitted code.

        Returns ``(ok, error_message)``. Each wrong guess is counted; once the
        allowance is used up the token is burned, so a 6-digit code cannot be
        walked through exhaustively.
        """
        if self.is_consumed:
            return False, "This code has already been used."
        if self.is_expired:
            return False, "This code has expired. Request a new one."
        if self.attempts >= max_attempts:
            self.consumed_at = utcnow()
            return False, "Too many incorrect attempts. Request a new code."

        self.attempts += 1

        if not check_password_hash(self.code_hash, (code or "").strip()):
            remaining = max_attempts - self.attempts
            if remaining <= 0:
                self.consumed_at = utcnow()
                return False, "Too many incorrect attempts. Request a new code."
            return False, f"Incorrect code. {remaining} attempt(s) remaining."

        self.consumed_at = utcnow()
        return True, None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<VerificationToken {self.purpose} user={self.user_id}>"


class Item(db.Model):
    """A found item logged into the registry."""

    __tablename__ = "items"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(50), nullable=False, default="Other", index=True)
    location = db.Column(db.String(150), nullable=False)

    # The finder's private description of a distinguishing feature. The admin
    # compares it against a claimant's proof. MUST NOT be rendered to anyone
    # other than an admin, or the verification step becomes meaningless.
    secret_detail = db.Column(db.Text, nullable=True)

    # Images live in object storage, not in this table. Previously the raw
    # bytes were base64-encoded into a Text column and every item's full image
    # was inlined into the homepage HTML, which grows the page without bound
    # and breaches Vercel's ~4.5 MB response cap after only a few uploads.
    image_url = db.Column(db.Text, nullable=True)
    thumbnail_url = db.Column(db.Text, nullable=True)
    image_public_id = db.Column(db.String(255), nullable=True)

    status = db.Column(
        db.String(30), nullable=False, default=ItemStatus.AVAILABLE, index=True
    )
    date_found = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    reported_by = db.Column(db.String(255), nullable=True)

    # AI Visual & Metadata fields
    ai_category = db.Column(db.String(50), nullable=True)
    ai_primary_color = db.Column(db.String(50), nullable=True)
    ai_secondary_colors = db.Column(db.JSON, nullable=True)
    ai_brand = db.Column(db.String(100), nullable=True)
    ai_model = db.Column(db.String(100), nullable=True)
    ai_visible_text = db.Column(db.JSON, nullable=True)
    ai_distinctive_features = db.Column(db.JSON, nullable=True)
    ai_condition = db.Column(db.String(30), nullable=True)
    ai_confidence = db.Column(db.Float, nullable=True)
    ai_analysis_status = db.Column(db.String(30), default="pending")
    ai_analyzed_at = db.Column(db.DateTime, nullable=True)

    claims = db.relationship(
        "Claim",
        back_populates="item",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="Claim.created_at.desc()",
    )

    @property
    def is_claimable(self) -> bool:
        return self.status == ItemStatus.AVAILABLE

    @property
    def display_thumbnail(self) -> str | None:
        """Best available small image, falling back to the full-size one."""
        return self.thumbnail_url or self.image_url

    def latest_claim(self) -> "Claim | None":
        return (
            Claim.query.filter_by(item_id=self.id)
            .order_by(Claim.created_at.desc())
            .first()
        )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Item {self.id} {self.name!r} {self.status}>"


class Claim(db.Model):
    """A student's request to collect an item."""

    __tablename__ = "claims"

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(
        db.Integer,
        db.ForeignKey("items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Always taken from the authenticated session, never from the request body.
    # The old endpoint read ``student_email`` out of the posted JSON and the
    # field was only ``readonly`` in HTML, so a hand-crafted request could file
    # a claim as any other student and redirect the approval notice to an
    # attacker-chosen address.
    claimant_email = db.Column(db.String(255), nullable=False, index=True)

    student_id = db.Column(db.String(50), nullable=False)
    phone = db.Column(db.String(32), nullable=True)
    proof_description = db.Column(db.Text, nullable=False)

    status = db.Column(
        db.String(20), nullable=False, default=ClaimStatus.PENDING, index=True
    )
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    decided_at = db.Column(db.DateTime, nullable=True)
    decision_remarks = db.Column(db.Text, nullable=True)

    item = db.relationship("Item", back_populates="claims")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Claim {self.id} item={self.item_id} {self.status}>"
