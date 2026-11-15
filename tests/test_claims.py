"""Item reporting and the claim workflow."""
import pytest
from sqlalchemy.exc import IntegrityError

from campus_retain.extensions import db
from campus_retain.models import AuditLog, Claim, ClaimStatus, Item, ItemStatus, Notification

from .conftest import api_token, login, make_college, make_item, make_user, png_bytes


@pytest.fixture
def world(new_client):
    college = make_college(pickup_instructions="Collect from Room 101 with your ID.", contact_email="lf@alpha.edu.in")
    make_user("s1@alpha.edu.in", college)
    make_user("s2@alpha.edu.in", college)
    make_user("admin@alpha.edu.in", college, role="college_admin")
    item = make_item(college)
    clients = {}
    for name in ("s1", "s2", "admin"):
        c = new_client()
        login(c, f"{name}@alpha.edu.in")
        clients[name] = (c, api_token(c))
    return college, item, clients


def claim(client_token, item_id, **body):
    c, token = client_token
    payload = {"item_id": item_id, "student_id": "21CS001", "phone": "", "proof_description": "Red sticker inside"}
    payload.update(body)
    return c.post("/api/claim", headers={"X-CSRFToken": token}, json=payload)


def admin_post(clients, path, **body):
    c, token = clients["admin"]
    return c.post(path, headers={"X-CSRFToken": token}, json=body)


def test_claim_uses_logged_in_identity(world, outbox):
    _, item, clients = world
    resp = claim(clients["s1"], item.id, student_email="victim@alpha.edu.in")
    assert resp.status_code == 200
    c = Claim.query.one()
    assert c.student_email == "s1@alpha.edu.in" and c.claimant.email == "s1@alpha.edu.in"
    assert c.status == ClaimStatus.PENDING
    assert {m["to"] for m in outbox} == {"s1@alpha.edu.in", "lf@alpha.edu.in"}
    assert Notification.query.filter_by(kind="claim.submitted").count() == 1


def test_second_active_claim_is_blocked(world):
    _, item, clients = world
    assert claim(clients["s1"], item.id).status_code == 200
    assert claim(clients["s2"], item.id).status_code == 409
    assert Claim.query.count() == 1


def test_database_enforces_one_active_claim_per_item(world):
    college, item, _ = world
    db.session.add(Claim(item_id=item.id, college_id=college.id, status=ClaimStatus.PENDING))
    db.session.add(Claim(item_id=item.id, college_id=college.id, status=ClaimStatus.APPROVED))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_reject_then_reclaim_then_approve_keeps_full_history(world, outbox):
    _, item, clients = world
    claim(clients["s1"], item.id)
    assert admin_post(clients, f"/api/admin/reject/{item.id}", remarks="Wrong colour").status_code == 200
    db.session.refresh(item)
    assert item.status == ItemStatus.AVAILABLE

    assert claim(clients["s2"], item.id).status_code == 200
    assert admin_post(clients, f"/api/admin/approve/{item.id}").status_code == 200
    db.session.refresh(item)
    assert item.status == ItemStatus.CLAIMED

    history = Claim.query.order_by(Claim.id).all()
    assert [(c.student_email, c.status) for c in history] == [
        ("s1@alpha.edu.in", ClaimStatus.REJECTED), ("s2@alpha.edu.in", ClaimStatus.APPROVED)]
    assert history[0].review_remarks == "Wrong colour"
    assert all(c.reviewed_by.email == "admin@alpha.edu.in" for c in history)
    approved_mail = [m for m in outbox if m["to"] == "s2@alpha.edu.in" and "approved" in m["subject"]]
    assert approved_mail and "Room 101" in approved_mail[0]["body"]
    actions = [a.action for a in AuditLog.query.order_by(AuditLog.id)]
    assert actions.count("claim.submitted") == 2 and "claim.rejected" in actions and "claim.approved" in actions


def test_approve_and_reject_need_a_pending_claim(world):
    _, item, clients = world
    assert admin_post(clients, f"/api/admin/approve/{item.id}").status_code == 409
    assert admin_post(clients, f"/api/admin/reject/{item.id}").status_code == 409


def test_claimant_never_sees_secret_detail(world):
    _, item, clients = world
    c, _ = clients["s1"]
    assert "TOPSECRET-STICKER" not in c.get("/dashboard").get_data(as_text=True)
    admin_client, _ = clients["admin"]
    assert "TOPSECRET-STICKER" in admin_client.get("/admin").get_data(as_text=True)


def test_reporter_cannot_claim_own_item(world):
    _, _, clients = world
    c, token = clients["s1"]
    c.post("/api/report", headers={"X-CSRFToken": token}, data={"name": "Calculator", "location": "Lab 2"})
    own = Item.query.filter_by(name="Calculator").one()
    assert claim(clients["s1"], own.id).status_code == 409


def test_remove_keeps_item_and_claim_history(world):
    _, item, clients = world
    claim(clients["s1"], item.id)
    assert admin_post(clients, f"/api/item/delete/{item.id}").status_code == 409  # pending claim
    admin_post(clients, f"/api/admin/reject/{item.id}", remarks="no")
    assert admin_post(clients, f"/api/item/delete/{item.id}").status_code == 200
    db.session.refresh(item)
    assert item.status == ItemStatus.REMOVED and item.removed_by_id is not None
    assert Claim.query.count() == 1
    c, _ = clients["s1"]
    assert "Black wallet" not in c.get("/dashboard").get_data(as_text=True)
    assert claim(clients["s2"], item.id).status_code == 404


def test_report_validation_and_image_processing(world):
    _, _, clients = world
    c, token = clients["s1"]
    h = {"X-CSRFToken": token}
    assert c.post("/api/report", headers=h, data={"name": "", "location": "x"}).status_code == 400
    assert c.post("/api/report", headers=h, data={"name": "x", "location": "y", "occurred_on": "2999-01-01"}).status_code == 400

    import io
    fake = {"name": "Phone", "location": "Cafe", "image": (io.BytesIO(b"<svg onload=alert(1)>"), "a.png", "image/png")}
    resp = c.post("/api/report", headers=h, data=fake, content_type="multipart/form-data")
    assert resp.status_code == 400 and "not a valid image" in resp.get_json()["error"]

    real = {"name": "Phone", "location": "Cafe", "description": "Blue case", "occurred_on": "2026-11-01",
            "image": (io.BytesIO(png_bytes((3000, 2000))), "p.png", "image/png")}
    resp = c.post("/api/report", headers=h, data=real, content_type="multipart/form-data")
    assert resp.status_code == 200
    item = Item.query.filter_by(name="Phone").one()
    assert item.image_data is None and len(item.images) == 1        # stored in object storage
    from PIL import Image
    from campus_retain.services.storage import get_storage
    stored = get_storage().get(item.images[0].storage_key)
    img = Image.open(io.BytesIO(stored))
    assert img.format == "JPEG" and max(img.size) <= 1600           # re-encoded, metadata stripped
    assert item.reported_by.email == "s1@alpha.edu.in" and item.description == "Blue case"


def test_oversized_upload_rejected(world, app):
    _, _, clients = world
    c, token = clients["s1"]
    import io
    big = io.BytesIO(b"\0" * (app.config["MAX_IMAGE_BYTES"] + 10))
    resp = c.post("/api/report", headers={"X-CSRFToken": token}, content_type="multipart/form-data",
                  data={"name": "x", "location": "y", "image": (big, "big.png", "image/png")})
    assert resp.status_code == 400


def test_claim_response_carries_finder_note_without_contact_details(new_client, outbox):
    """The paper-plane note shows who reported the item, but never their email or phone."""
    college = make_college()
    finder = make_user("finder@alpha.edu.in", college)
    finder.full_name, finder.phone, finder.student_id = "Priya Sharma Rao", "9999988888", "21EC042"
    finder.department_name = "Electronics"
    db.session.commit()
    item = make_item(college, reporter=finder, location="Main library, 2nd floor")
    make_user("owner@alpha.edu.in", college)
    c = new_client()
    login(c, "owner@alpha.edu.in")

    resp = claim((c, api_token(c)), item.id)
    assert resp.status_code == 200
    note = resp.get_json()["finder"]
    assert note["name"] == "Priya R."
    assert note["role"] == "Student" and note["department"] == "Electronics"
    assert note["found_at"] == "Main library, 2nd floor" and note["ref"].startswith("F-")
    body = resp.get_data(as_text=True)
    assert "finder@alpha.edu.in" not in body and "9999988888" not in body and "21EC042" not in body
    assert "TOPSECRET" not in body


def test_finder_note_falls_back_when_reporter_has_no_name(world):
    _, item, clients = world   # item has no reporter at all
    note = claim(clients["s1"], item.id).get_json()["finder"]
    assert note["name"] == "Someone on campus" and note["role"] is None


def test_finder_contact_is_shared_only_after_approval(new_client, outbox):
    college = make_college()
    finder = make_user("finder@alpha.edu.in", college)
    finder.full_name, finder.phone = "Priya Sharma", "9999988888"
    db.session.commit()
    item = make_item(college, reporter=finder)
    make_user("owner@alpha.edu.in", college)
    make_user("admin@alpha.edu.in", college, role="college_admin")
    owner, admin = new_client(), new_client()
    login(owner, "owner@alpha.edu.in")
    login(admin, "admin@alpha.edu.in")
    claim((owner, api_token(owner)), item.id)

    pending = owner.get("/api/v1/me/activity").get_json()["claims"][0]
    assert pending["finder"] is None
    assert "finder@alpha.edu.in" not in owner.get("/api/v1/me/activity").get_data(as_text=True)

    assert admin.post(f"/api/admin/approve/{item.id}", headers={"X-CSRFToken": api_token(admin)}, json={}).status_code == 200
    note = owner.get("/api/v1/me/activity").get_json()["claims"][0]["finder"]
    assert note["name"] == "Priya Sharma"
    assert note["email"] == "finder@alpha.edu.in" and note["phone"] == "9999988888"
