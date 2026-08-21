"""Database-backed rate limiting.

Why not Flask-Limiter: its default storage is in-process memory, and on Vercel
every request may be served by a cold process. An in-memory counter would reset
constantly and enforce nothing, while appearing to work in local testing. The
honest options on serverless are a shared cache (Redis, another service to run)
or the database that is already there. This uses the database.

Only coarse abuse limits belong here. The two most valuable protections are
implemented in the domain model instead, where they can be precise:
``User.failed_logins``/``locked_until`` for credential stuffing, and
``VerificationToken.created_at`` for OTP resend flooding.
"""

from __future__ import annotations

import hashlib
from datetime import timedelta

from flask import current_app, request

from app.extensions import db
from app.models import utcnow


class RateLimitHit(db.Model):
    """One recorded action, used to count activity inside a time window."""

    __tablename__ = "rate_limit_hits"

    id = db.Column(db.Integer, primary_key=True)
    bucket = db.Column(db.String(64), nullable=False, index=True)
    identity = db.Column(db.String(64), nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    __table_args__ = (
        db.Index("ix_rate_limit_lookup", "bucket", "identity", "created_at"),
    )


def client_identity() -> str:
    """A stable, non-identifying key for the caller.

    The raw address is hashed rather than stored: a table of student IP
    addresses is a privacy liability with no operational benefit, since the
    only thing needed is equality between requests.
    """
    forwarded = request.headers.get("X-Forwarded-For", "")
    # Vercel appends the true client address; the leftmost entry is the client.
    address = (forwarded.split(",")[0].strip() if forwarded else "") or (
        request.remote_addr or "unknown"
    )
    salt = current_app.config.get("SECRET_KEY", "")
    return hashlib.sha256(f"{salt}:{address}".encode()).hexdigest()[:64]


def check(bucket: str, limit: int, per_seconds: int, identity: str | None = None):
    """Record an action and report whether the caller is over the limit.

    Returns ``(allowed, retry_after_seconds)``. Failures are non-fatal: if the
    limiter itself errors, the request is allowed through rather than taking the
    site down.
    """
    ident = identity or client_identity()
    window_start = utcnow() - timedelta(seconds=per_seconds)

    try:
        recent = (
            RateLimitHit.query.filter(
                RateLimitHit.bucket == bucket,
                RateLimitHit.identity == ident,
                RateLimitHit.created_at >= window_start,
            )
            .order_by(RateLimitHit.created_at.asc())
            .all()
        )

        if len(recent) >= limit:
            oldest = recent[0].created_at
            retry_after = int(
                (oldest + timedelta(seconds=per_seconds) - utcnow()).total_seconds()
            )
            return False, max(1, retry_after)

        db.session.add(RateLimitHit(bucket=bucket, identity=ident))
        db.session.commit()
        return True, 0

    except Exception:
        current_app.logger.exception("Rate limiter unavailable; allowing request")
        db.session.rollback()
        return True, 0


def prune(older_than_seconds: int = 24 * 3600) -> int:
    """Delete expired rows. Invoked by the ``flask prune-rate-limits`` command."""
    cutoff = utcnow() - timedelta(seconds=older_than_seconds)
    deleted = RateLimitHit.query.filter(RateLimitHit.created_at < cutoff).delete()
    db.session.commit()
    return int(deleted or 0)
