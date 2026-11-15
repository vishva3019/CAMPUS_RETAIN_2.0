"""Claim workflow. Claims are never overwritten: each one keeps its own status,
reviewer and remarks. A partial unique index guarantees one active claim per item."""
import secrets
from datetime import timedelta

from flask import current_app
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db
from ..models import Claim, ClaimStatus, Item, ItemKind, ItemStatus, utcnow
from ..security import tenant_query
from .audit import audit, notify
from .messaging import send_email, send_sms


def claim_link(claim):
    """Where a notification about this claim should take the student (React app)."""
    return f"/app/activity?claim={claim.id}"


class ClaimError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _locked_item(item_id):
    item = tenant_query(Item).filter(Item.id == item_id).with_for_update().first()
    if item is None or item.status == ItemStatus.REMOVED:
        raise ClaimError("Item not found.", 404)
    return item


def submit_claim(user, item_id, student_id, phone, proof, item=None):
    """`item` is passed (already locked) for claims through the inter-college network."""
    item = item if item is not None else _locked_item(item_id)
    if item.kind != ItemKind.FOUND:
        raise ClaimError("Only found items can be claimed.", 409)
    if item.status != ItemStatus.AVAILABLE:
        raise ClaimError("This item already has a claim under review or has been claimed.", 409)
    if item.reported_by_id == user.id:
        raise ClaimError("You reported this item, so you can't claim it.", 409)

    claim = Claim(
        item_id=item.id, college_id=item.college_id, claimant_id=user.id,
        student_email=user.email, student_id=student_id, phone=phone,
        proof_description=proof, status=ClaimStatus.PENDING,
    )
    item.status = ItemStatus.PENDING
    db.session.add(claim)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        raise ClaimError("This item already has a claim under review.", 409)
    audit("claim.submitted", claim, item_id=item.id)
    notify(user, "claim.submitted", f"Claim submitted for {item.name}",
           "Staff will review your ownership details. You'll be told as soon as they decide.",
           link=claim_link(claim))
    db.session.commit()

    college = item.college
    send_email(user.email, f"Claim submitted: {item.name}",
               f"Your claim for '{item.name}' was received and is under review.\n"
               "You will get an email when staff decide.", college=college)
    if college.contact_email:
        send_email(college.contact_email, f"New claim: {item.name}",
                   f"A claim was submitted for '{item.name}' (item #{item.id}).\n"
                   "Review it in the Campus Retain admin dashboard.", college=college)
    send_sms(phone, f"Campus Retain: claim for {item.name} submitted.")
    return claim


def _active_claim(item):
    claim = (Claim.query.filter(Claim.item_id == item.id, Claim.status == ClaimStatus.PENDING)
             .order_by(Claim.timestamp.desc()).first())
    if claim is None:
        raise ClaimError("This item has no claim waiting for review.", 409)
    return claim


def approve_claim(reviewer, item_id, remarks=None):
    item = _locked_item(item_id)
    if item.status != ItemStatus.PENDING:
        raise ClaimError("Only items with a pending claim can be approved.", 409)
    claim = _active_claim(item)
    claim.status = ClaimStatus.APPROVED
    claim.reviewed_by_id, claim.reviewed_at = reviewer.id, utcnow()
    claim.review_remarks = remarks or None
    item.status = ItemStatus.CLAIMED
    code = _new_pickup_code(claim)
    from .matching import confirm_matches_for
    confirm_matches_for(claim)
    audit("claim.approved", claim, item_id=item.id)
    college = reviewer.college
    pickup = pickup_instructions(item, college)
    notify(claim.claimant, "claim.approved", f"Claim approved: {item.name}. Your pickup code is ready",
           pickup + " Open the claim to see your pickup code (it was also emailed to you).",
           link=claim_link(claim))
    db.session.commit()

    _send_pickup_code(claim, item, college, code, approved=True)
    return claim


# ---------------------------------------------------------------- pickup

def pickup_instructions(item, college):
    if item.collection_point is not None:
        text = item.collection_point.pickup_text()
        if college.pickup_instructions:
            text += " " + college.pickup_instructions
        return text
    return college.pickup_instructions or (
        f"Collect it from {college.support_office}." if college.support_office
        else "Staff will contact you with pickup details.")


def _new_pickup_code(claim):
    """Replace any previous code. Only the hash is stored; the code goes by email/SMS."""
    code = f"{secrets.randbelow(1_000_000):06d}"
    now = utcnow()
    claim.pickup_code_hash = generate_password_hash(code)
    claim.pickup_code_sent_at = now
    claim.pickup_code_expires_at = now + timedelta(days=current_app.config["PICKUP_CODE_TTL_DAYS"])
    claim.pickup_code_attempts = 0
    return code


def _send_pickup_code(claim, item, college, code, approved=False):
    pickup = pickup_instructions(item, college)
    days = current_app.config["PICKUP_CODE_TTL_DAYS"]
    intro = (f"Good news! Your claim for '{item.name}' was approved." if approved
             else f"Here is a new pickup code for '{item.name}'. Earlier codes no longer work.")
    send_email(claim.student_email,
               f"Claim approved: {item.name}" if approved else f"New pickup code: {item.name}",
               f"{intro}\n\n{pickup}\n\nYour pickup code: {code}\n\n"
               f"Show this code and your college ID card to staff when you collect the item. "
               f"The code works for {days} days. Don't share it with anyone else.",
               college=college)
    send_sms(claim.phone, f"Campus Retain: pickup code for {item.name}: {code}. {pickup}"[:300])


def resend_pickup_code(user, claim_id):
    # A claim made through the network belongs to another college: read it across RLS.
    from ..rls import rls_bypass
    with rls_bypass():
        return _resend_pickup_code(user, claim_id)


def _resend_pickup_code(user, claim_id):
    claim = (Claim.query.filter(Claim.id == claim_id, Claim.claimant_id == user.id)
             .with_for_update().first())
    if claim is None:
        raise ClaimError("Claim not found.", 404)
    if claim.status != ClaimStatus.APPROVED:
        raise ClaimError("Pickup codes are only for approved claims that haven't been collected.", 409)
    wait = current_app.config["PICKUP_CODE_RESEND_SECONDS"]
    if claim.pickup_code_sent_at and utcnow() - claim.pickup_code_sent_at < timedelta(seconds=wait):
        raise ClaimError("A code was sent less than a minute ago. Check your email, or try again shortly.", 429)
    code = _new_pickup_code(claim)
    audit("pickup.code_resent", claim, item_id=claim.item_id)
    db.session.commit()
    _send_pickup_code(claim, claim.item, claim.item.college, code)
    # Shown once to the signed-in claimant (the same person the email goes to). Never stored.
    claim.issued_code = code
    return claim


def verify_pickup(staff, claim_id, code):
    """Security desk: confirm the handover with the claimant's code."""
    claim = tenant_query(Claim).filter(Claim.id == claim_id).with_for_update().first()
    if claim is None:
        raise ClaimError("Claim not found.", 404)
    item = claim.item
    if (staff.campus_id and staff.role_name != "college_admin"
            and item.campus_id and item.campus_id != staff.campus_id):
        raise ClaimError("This item belongs to another campus.", 403)
    if claim.status != ClaimStatus.APPROVED:
        raise ClaimError("This claim isn't waiting for pickup.", 409)
    max_attempts = current_app.config["PICKUP_CODE_MAX_ATTEMPTS"]
    if not claim.pickup_code_hash:
        # Claims approved before pickup codes existed (or imported from 2.0).
        raise ClaimError("No pickup code has been sent for this claim yet. Ask the student to "
                         "send one from 'My activity', then enter it here.", 409)
    if claim.pickup_code_attempts >= max_attempts:
        raise ClaimError("Too many wrong codes. Ask the student to send a new code from "
                         "'My activity', then try again.", 423)
    if claim.pickup_code_expires_at and utcnow() > claim.pickup_code_expires_at:
        raise ClaimError("This code has expired. Ask the student to send a new code from "
                         "'My activity'.", 410)
    code = (code or "").strip()
    if not (code.isdigit() and len(code) == 6 and check_password_hash(claim.pickup_code_hash, code)):
        claim.pickup_code_attempts += 1
        left = max_attempts - claim.pickup_code_attempts
        audit("pickup.code_failed", claim, item_id=item.id, attempts=claim.pickup_code_attempts)
        db.session.commit()
        raise ClaimError("That code isn't right." + (f" {left} tries left." if left > 0 else
                         " No tries left: the student must send a new code."), 400)

    now = utcnow()
    claim.status = ClaimStatus.COLLECTED
    claim.collected_at, claim.collected_by_id = now, staff.id
    claim.pickup_code_hash = None
    item.status = ItemStatus.RETURNED
    audit("pickup.collected", claim, item_id=item.id)
    notify(claim.claimant, "claim.collected", f"Returned to you: {item.name}",
           "Your item was handed over. Thanks for using Campus Retain.", link=claim_link(claim))
    if item.reported_by and item.reported_by_id != claim.claimant_id:
        notify(item.reported_by, "item.returned", f"Returned to its owner: {item.name}",
               "The item you reported has been collected by its owner. Thank you!",
               link="/app/activity?tab=reports")
    db.session.commit()
    send_email(claim.student_email, f"Collected: {item.name}",
               f"Staff confirmed that you collected '{item.name}' on "
               f"{now.strftime('%d %b %Y, %H:%M')} UTC. If this wasn't you, contact your "
               "college's lost-and-found office straight away.", college=staff.college)
    return claim


def withdraw_claim(user, claim_id):
    from ..rls import rls_bypass
    with rls_bypass():
        return _withdraw_claim(user, claim_id)


def _withdraw_claim(user, claim_id):
    claim = (Claim.query.filter_by(id=claim_id, claimant_id=user.id)
             .with_for_update().first())
    if claim is None:
        raise ClaimError("Claim not found.", 404)
    if claim.status != ClaimStatus.PENDING:
        raise ClaimError("Only claims still under review can be withdrawn.", 409)
    claim.status = ClaimStatus.WITHDRAWN
    if claim.item.status == ItemStatus.PENDING:
        claim.item.status = ItemStatus.AVAILABLE
    audit("claim.withdrawn", claim, item_id=claim.item_id)
    db.session.commit()
    return claim


def close_lost_report(user, item_id, action):
    """Owner closes their own open lost report: 'found' (got it back) or 'withdraw'."""
    if action not in ("found", "withdraw"):
        raise ClaimError("Unknown action.", 400)
    item = (Item.query.filter_by(id=item_id, reported_by_id=user.id, college_id=user.college_id,
                                 kind=ItemKind.LOST, status=ItemStatus.AVAILABLE).first())
    if item is None:
        raise ClaimError("That lost-item report is already closed.", 404)
    if action == "found":
        item.status = ItemStatus.RETURNED
    else:
        item.status = ItemStatus.REMOVED
        item.removed_at, item.removed_by_id = utcnow(), user.id
    audit("lost.closed", item, outcome=action)
    db.session.commit()
    return item


def reject_claim(reviewer, item_id, remarks):
    item = _locked_item(item_id)
    if item.status != ItemStatus.PENDING:
        raise ClaimError("Only items with a pending claim can be rejected.", 409)
    claim = _active_claim(item)
    remarks = remarks or "The details provided did not match the item."
    claim.status = ClaimStatus.REJECTED
    claim.reviewed_by_id, claim.reviewed_at = reviewer.id, utcnow()
    claim.review_remarks = remarks
    item.status = ItemStatus.AVAILABLE
    audit("claim.rejected", claim, item_id=item.id)
    notify(claim.claimant, "claim.rejected", f"Claim not approved: {item.name}", remarks,
           link=claim_link(claim))
    db.session.commit()

    send_email(claim.student_email, f"Claim update: {item.name}",
               f"Your claim for '{item.name}' was reviewed and not approved.\n\n"
               f"Remarks from staff: {remarks}", college=reviewer.college)
    send_sms(claim.phone, f"Campus Retain: claim for {item.name} not approved. {remarks}"[:300])
    return claim


def send_pickup_reminders():
    """Remind students once about approved claims not collected after
    PICKUP_REMINDER_DAYS. Returns how many were sent. Run daily (cron or CLI)."""
    from ..rls import rls_bypass
    days = current_app.config["PICKUP_REMINDER_DAYS"]
    cutoff = utcnow() - timedelta(days=days)
    sent = 0
    with rls_bypass():
        claims = (Claim.query.filter(Claim.status == ClaimStatus.APPROVED, Claim.reviewed_at <= cutoff,
                                     Claim.pickup_reminded_at.is_(None)).limit(500).all())
        for claim in claims:
            item = claim.item
            claim.pickup_reminded_at = utcnow()
            if claim.claimant is None:
                continue
            pickup = pickup_instructions(item, item.college)
            notify(claim.claimant, "pickup.reminder", f"Reminder: collect your {item.name}",
                   pickup + " Bring your college ID and your pickup code.", link=claim_link(claim))
            send_email(claim.student_email, f"Reminder: your {item.name} is waiting",
                       f"Your claim for '{item.name}' was approved {days}+ days ago and the item hasn't "
                       f"been collected yet.\n\n{pickup}\n\nOpen Campus Retain to see your pickup code.",
                       college=item.college)
            sent += 1
        db.session.commit()
    return sent
