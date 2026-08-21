"""Outbound SMS via Twilio.

Optional by design: if Twilio credentials are absent the app degrades to
email-only notifications rather than erroring. Import of the Twilio SDK is lazy
so the package is not required to run the test suite or a local dev server.
"""

from __future__ import annotations

import re

from flask import current_app

_DIGITS = re.compile(r"\D")


def is_configured() -> bool:
    cfg = current_app.config
    return bool(
        cfg.get("TWILIO_ACCOUNT_SID")
        and cfg.get("TWILIO_AUTH_TOKEN")
        and cfg.get("TWILIO_PHONE_NUMBER")
    )


def normalise_number(raw: str) -> str | None:
    """Coerce user input into E.164, or return ``None`` if implausible.

    Accepts the shapes students actually type: ``9686193049``,
    ``096861 93049``, ``+91 96861-93049``.
    """
    if not raw:
        return None

    raw = raw.strip()
    explicit_plus = raw.startswith("+")
    digits = _DIGITS.sub("", raw)

    if not digits:
        return None

    if explicit_plus:
        return f"+{digits}" if 8 <= len(digits) <= 15 else None

    country = current_app.config.get("SMS_DEFAULT_COUNTRY_CODE", "+91")

    # A leading trunk zero is common when typing a local number.
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]

    if len(digits) == 10:
        return f"{country}{digits}"

    # Already includes a country code without the plus sign.
    if 11 <= len(digits) <= 15:
        return f"+{digits}"

    return None


def send_sms(to: str, body: str) -> bool:
    """Best-effort SMS. Returns ``False`` instead of raising on any failure."""
    if not is_configured():
        current_app.logger.debug("Twilio not configured; skipping SMS")
        return False

    number = normalise_number(to)
    if not number:
        current_app.logger.warning("Skipping SMS: unusable phone number")
        return False

    try:
        from twilio.rest import Client  # imported lazily; optional dependency
    except ImportError:
        current_app.logger.warning("twilio package not installed; skipping SMS")
        return False

    cfg = current_app.config
    try:
        client = Client(cfg["TWILIO_ACCOUNT_SID"], cfg["TWILIO_AUTH_TOKEN"])
        client.messages.create(
            body=body, from_=cfg["TWILIO_PHONE_NUMBER"], to=number
        )
    except Exception:
        # Twilio raises a broad family of exceptions; none should reach a user.
        current_app.logger.exception("Failed to send SMS")
        return False

    current_app.logger.info("SMS dispatched")
    return True
