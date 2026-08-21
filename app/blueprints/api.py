"""JSON endpoints backing the front end.

Every handler here returns JSON, including on failure, and none of them ever
place an exception string in the response body. The previous implementation
returned ``jsonify({"error": str(e)}), 500``, which leaked database schema
details and file paths to anyone who could provoke an error.
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from app.extensions import db
from app.models import Claim, ClaimStatus, Item, ItemStatus, utcnow
from app.security import (
    admin_required,
    current_user_email,
    login_required,
)
from app.services import notifications
from app.services.storage import StorageError, get_storage, read_validated_image

bp = Blueprint("api", __name__, url_prefix="/api")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _error(message: str, status: int = 400):
    return jsonify({"ok": False, "error": message}), status


def _ok(payload: dict | None = None, status: int = 200):
    body = {"ok": True}
    if payload:
        body.update(payload)
    return jsonify(body), status


def _clean(raw: object, limit: int) -> str:
    """Trim a submitted string and cap its length."""
    if not isinstance(raw, str):
        return ""
    return raw.strip()[:limit]


# ---------------------------------------------------------------------------
# Reporting a found item
# ---------------------------------------------------------------------------

@bp.post("/items")
@login_required
def report_item():
    form = request.form

    name = _clean(form.get("name"), 120)
    location = _clean(form.get("location"), 150)
    category = _clean(form.get("category"), 50) or "Other"
    secret_detail = _clean(form.get("secret_detail"), 2000)

    if not name:
        return _error("Please give the item a short name.")
    if not location:
        return _error("Please say where you found it.")
    if category not in current_app.config["ITEM_CATEGORIES"]:
        category = "Other"

    try:
        validated = read_validated_image(request.files.get("image"))
    except StorageError as exc:
        return _error(str(exc))

    stored = None
    if validated is not None:
        data, extension = validated
        try:
            stored = get_storage().save(data, extension)
        except StorageError as exc:
            return _error(str(exc))

    item = Item(
        name=name,
        category=category,
        location=location,
        secret_detail=secret_detail or None,
        reported_by=current_user_email(),
        image_url=stored.url if stored else None,
        thumbnail_url=stored.thumbnail_url if stored else None,
        image_public_id=stored.public_id if stored else None,
    )
    db.session.add(item)
    db.session.commit()

    notifications.notify_item_reported(item)
    return _ok({"item_id": item.id}, status=201)


# ---------------------------------------------------------------------------
# Claiming an item
# ---------------------------------------------------------------------------

@bp.post("/claims")
@login_required
def create_claim():
    payload = request.get_json(silent=True) or {}

    item_id = payload.get("item_id")
    try:
        item_id = int(item_id)
    except (TypeError, ValueError):
        return _error("Missing or invalid item reference.")

    student_id = _clean(payload.get("student_id"), 50)
    phone = _clean(payload.get("phone"), 32)
    proof = _clean(payload.get("proof_description"), 2000)

    if not student_id:
        return _error("Please enter your student ID.")
    if not proof:
        return _error("Please describe something that identifies the item as yours.")

    item = db.session.get(Item, item_id)
    if item is None:
        return _error("That item is no longer listed.", 404)

    if item.status != ItemStatus.AVAILABLE:
        return _error(
            "Someone has already claimed this item and it is under review.", 409
        )

    # Identity comes from the session, never from the request body. The old
    # endpoint trusted a ``student_email`` field that was merely marked
    # ``readonly`` in the HTML, so a hand-built request could file a claim in
    # another student's name and have the approval notice sent elsewhere.
    claimant_email = current_user_email()
    if not claimant_email:
        return _error("Your session has expired. Please sign in again.", 401)

    duplicate = Claim.query.filter_by(
        item_id=item.id,
        claimant_email=claimant_email,
        status=ClaimStatus.PENDING,
    ).first()
    if duplicate is not None:
        return _error("You already have a claim awaiting review on this item.", 409)

    claim = Claim(
        item_id=item.id,
        claimant_email=claimant_email,
        student_id=student_id,
        phone=phone or None,
        proof_description=proof,
    )
    item.status = ItemStatus.PENDING

    db.session.add(claim)
    db.session.commit()

    notifications.notify_claim_submitted(claim, item)
    return _ok({"claim_id": claim.id}, status=201)


# ---------------------------------------------------------------------------
# Administrator decisions
# ---------------------------------------------------------------------------

@bp.post("/admin/claims/<int:claim_id>/approve")
@admin_required
def approve_claim(claim_id: int):
    """Approve one specific claim.

    Keyed on the claim rather than the item, because two students can claim the
    same item. The previous endpoint took an item id and silently acted on
    whichever claim happened to be newest, which meant the admin could not
    choose between competing claimants.
    """
    claim = db.session.get(Claim, claim_id)
    if claim is None:
        return _error("That claim no longer exists.", 404)
    if claim.status != ClaimStatus.PENDING:
        return _error(f"This claim was already {claim.status.lower()}.", 409)

    item = claim.item
    now = utcnow()

    claim.status = ClaimStatus.APPROVED
    claim.decided_at = now
    item.status = ItemStatus.CLAIMED

    # Competing claims on the same item cannot also succeed. Closing them here
    # means nobody is left waiting on a decision that will never come.
    superseded = [
        other
        for other in Claim.query.filter_by(
            item_id=item.id, status=ClaimStatus.PENDING
        ).all()
        if other.id != claim.id
    ]
    remark = "Another claimant's proof of ownership matched this item."
    for other in superseded:
        other.status = ClaimStatus.REJECTED
        other.decided_at = now
        other.decision_remarks = remark

    db.session.commit()

    notifications.notify_claim_approved(claim, item)
    for other in superseded:
        notifications.notify_claim_rejected(other, item, remark)

    return _ok({"status": item.status, "superseded": len(superseded)})


@bp.post("/admin/claims/<int:claim_id>/reject")
@admin_required
def reject_claim(claim_id: int):
    payload = request.get_json(silent=True) or {}
    remarks = _clean(payload.get("remarks"), 1000)
    if not remarks:
        remarks = "The details provided did not match this item."

    claim = db.session.get(Claim, claim_id)
    if claim is None:
        return _error("That claim no longer exists.", 404)
    if claim.status != ClaimStatus.PENDING:
        return _error(f"This claim was already {claim.status.lower()}.", 409)

    item = claim.item

    claim.status = ClaimStatus.REJECTED
    claim.decided_at = utcnow()
    claim.decision_remarks = remarks

    # Return the item to the register only if nothing else is pending on it.
    others_pending = (
        Claim.query.filter_by(item_id=item.id, status=ClaimStatus.PENDING)
        .filter(Claim.id != claim.id)
        .count()
    )
    if others_pending == 0 and item.status == ItemStatus.PENDING:
        item.status = ItemStatus.AVAILABLE

    db.session.commit()

    notifications.notify_claim_rejected(claim, item, remarks)
    return _ok({"status": item.status})


@bp.post("/admin/items/<int:item_id>/delete")
@admin_required
def delete_item(item_id: int):
    item = db.session.get(Item, item_id)
    if item is None:
        return _error("That item no longer exists.", 404)

    # Remove the stored image too, otherwise deleted items leave orphaned files
    # consuming the storage quota forever.
    public_id = item.image_public_id
    if public_id:
        try:
            get_storage().delete(public_id)
        except StorageError:
            current_app.logger.warning("Could not delete stored image %s", public_id)

    db.session.delete(item)
    db.session.commit()
    return _ok()
