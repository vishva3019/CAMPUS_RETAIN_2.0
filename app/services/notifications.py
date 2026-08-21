"""Notification orchestration.

Each function corresponds to one domain event. Emails for a single event are
handed to :func:`app.services.mail.send_messages` as one batch so they share a
single SMTP connection, and SMS is always attempted after email because it is
the less reliable channel.

Nothing here raises. A notification failure must never roll back the database
change that triggered it -- a student's claim is recorded whether or not the
confirmation email lands.
"""

from __future__ import annotations

from flask import current_app

from app.models import Claim, Item, User
from app.services import sms
from app.services.mail import OutboundEmail, send_messages


def _admin_email() -> str | None:
    return current_app.config.get("ADMIN_EMAIL") or None


def _where() -> str:
    return current_app.config.get("SUPPORT_LOCATION", "DOSS office")


def _site() -> str:
    return current_app.config.get("SITE_NAME", "CampusRetain")


# ---------------------------------------------------------------------------
# Account lifecycle
# ---------------------------------------------------------------------------

def send_verification_code(user: User, code: str) -> bool:
    minutes = current_app.config["OTP_TTL_MINUTES"]
    body = (
        f"Welcome to {_site()}.\n\n"
        f"Your verification code is: {code}\n\n"
        f"Enter it on the sign-up page to activate your account. "
        f"The code expires in {minutes} minutes.\n\n"
        "If you did not request an account, you can ignore this email -- "
        "no account will be created without this code."
    )
    return send_messages(
        [
            OutboundEmail(
                to=user.email,
                subject=f"{_site()} - Verify your email",
                body=body,
            )
        ]
    ) == 1


def send_password_reset_code(user: User, code: str) -> bool:
    minutes = current_app.config["OTP_TTL_MINUTES"]
    body = (
        f"A password reset was requested for your {_site()} account.\n\n"
        f"Your verification code is: {code}\n\n"
        f"The code expires in {minutes} minutes.\n\n"
        "If you did not request this, no action is needed and your password "
        "remains unchanged."
    )
    return send_messages(
        [
            OutboundEmail(
                to=user.email,
                subject=f"{_site()} - Password reset code",
                body=body,
            )
        ]
    ) == 1


# ---------------------------------------------------------------------------
# Item and claim lifecycle
# ---------------------------------------------------------------------------

def notify_item_reported(item: Item) -> None:
    admin = _admin_email()
    if not admin:
        return
    body = (
        f"A new found item has been logged.\n\n"
        f"Item: {item.name}\n"
        f"Category: {item.category}\n"
        f"Found at: {item.location}\n"
        f"Reported by: {item.reported_by or 'unknown'}\n\n"
        f"Review it in the admin dashboard."
    )
    send_messages(
        [OutboundEmail(to=admin, subject=f"{_site()}: new item reported", body=body)]
    )


def notify_claim_submitted(claim: Claim, item: Item) -> None:
    messages = [
        OutboundEmail(
            to=claim.claimant_email,
            subject=f"{_site()} - Claim submitted",
            body=(
                f"Your claim for '{item.name}' has been submitted and is "
                f"awaiting review.\n\n"
                f"You will be notified by email once it has been assessed. "
                f"Please do not visit the {_where()} until your claim is "
                f"approved."
            ),
        )
    ]

    admin = _admin_email()
    if admin:
        messages.append(
            OutboundEmail(
                to=admin,
                subject=f"{_site()}: new claim on '{item.name}'",
                body=(
                    f"A claim has been submitted.\n\n"
                    f"Item: {item.name}\n"
                    f"Claimant: {claim.claimant_email}\n"
                    f"Student ID: {claim.student_id}\n"
                    f"Phone: {claim.phone or 'not provided'}\n\n"
                    f"Their stated proof of ownership:\n{claim.proof_description}\n\n"
                    f"Compare this against the finder's private note in the "
                    f"admin dashboard before approving."
                ),
            )
        )

    send_messages(messages)
    sms.send_sms(
        claim.phone or "",
        f"{_site()}: your claim for {item.name} was submitted and is under review.",
    )


def notify_claim_approved(claim: Claim, item: Item) -> None:
    send_messages(
        [
            OutboundEmail(
                to=claim.claimant_email,
                subject=f"{_site()} - Claim approved",
                body=(
                    f"Good news: your claim for '{item.name}' has been "
                    f"approved.\n\n"
                    f"Please collect the item from the {_where()} and bring "
                    f"your student ID.\n\n"
                    f"If you can no longer collect it, reply to this email so "
                    f"the item can be returned to the register."
                ),
            )
        ]
    )
    sms.send_sms(
        claim.phone or "",
        f"{_site()}: claim approved for {item.name}. "
        f"Collect it from the {_where()} with your student ID.",
    )


def notify_claim_rejected(claim: Claim, item: Item, remarks: str) -> None:
    send_messages(
        [
            OutboundEmail(
                to=claim.claimant_email,
                subject=f"{_site()} - Claim not approved",
                body=(
                    f"Your claim for '{item.name}' was reviewed and could not "
                    f"be approved.\n\n"
                    f"Reason: {remarks}\n\n"
                    f"The item has been returned to the register. If you "
                    f"believe this was a mistake, visit the {_where()} with "
                    f"any supporting evidence."
                ),
            )
        ]
    )
    sms.send_sms(
        claim.phone or "",
        f"{_site()}: claim for {item.name} was not approved. Reason: {remarks}",
    )
