"""Phase 2: photo storage (memory + R2 via a local S3 server), collection points,
pickup codes at the security desk, lost-item reports and My activity."""
import base64
import io

import pytest

from campus_retain.config import ConfigError, load_config
from campus_retain.extensions import db
from campus_retain.models import (AuditLog, Claim, ClaimStatus, CollectionPoint, Item, ItemKind,
                                  ItemStatus, Notification)
from campus_retain.services.storage import get_storage

from .conftest import (api_token, last_code, login, make_campus, make_college, make_item,
                       make_user, png_bytes)


@pytest.fixture
def world(new_client):
    college = make_college(contact_email="lf@alpha.edu.in")
    other = make_college(slug="beta", domains=("beta.edu.in",))
    for email, c, role in [("s1@alpha.edu.in", college, "student"), ("s2@alpha.edu.in", college, "student"),
                           ("admin@alpha.edu.in", college, "college_admin"),
                           ("guard@alpha.edu.in", college, "security_staff"),
                           ("s9@beta.edu.in", other, "student"), ("guard@beta.edu.in", other, "security_staff")]:
        make_user(email, c, role=role)
    clients = {}
    for name in ("s1@alpha.edu.in", "s2@alpha.edu.in", "admin@alpha.edu.in", "guard@alpha.edu.in",
                 "s9@beta.edu.in", "guard@beta.edu.in"):
        cl = new_client()
        login(cl, name)
        clients[name.split(".")[0]] = (cl, api_token(cl))
    return college, other, clients


def fresh(resp):
    """Requests commit in their own session; drop the test session's cached rows."""
    db.session.expire_all()
    return resp


def report(client_token, **data):
    c, token = client_token
    files = data.pop("files", [])
    form = {"name": "Blue bottle", "location": "Library", **data}
    if files:
        form["images"] = [(io.BytesIO(b), f"p{i}.png", "image/png") for i, b in enumerate(files)]
    return fresh(c.post("/api/report", headers={"X-CSRFToken": token}, data=form, content_type="multipart/form-data"))


def post_json(client_token, path, **body):
    c, token = client_token
    return fresh(c.post(path, headers={"X-CSRFToken": token}, json=body))


def form_post(client_token, path, **data):
    c, token = client_token
    return fresh(c.post(path, data={"csrf_token": token, **data}))


# ---------------------------------------------------------------- photos

def test_photos_go_to_storage_and_are_served_only_inside_the_college(world):
    _, _, clients = world
    resp = report(clients["s1@alpha"], files=[png_bytes(), png_bytes(color=(0, 0, 200))])
    assert resp.status_code == 200
    item = db.session.get(Item, resp.get_json()["id"])
    assert item.image_data is None and [i.position for i in item.images] == [0, 1]
    key = item.images[0].storage_key
    assert key.startswith(f"colleges/{item.college_id}/items/") and key.endswith(".jpg")

    url = f"/media/item-image/{item.images[0].id}"
    ok = clients["s2@alpha"][0].get(url)
    assert ok.status_code == 200 and ok.mimetype == "image/jpeg" and ok.data[:2] == b"\xff\xd8"
    assert "private" in ok.headers["Cache-Control"]
    assert clients["s9@beta"][0].get(url).status_code == 404          # other college
    assert clients["s1@alpha"][0].application.test_client().get(url).status_code == 302   # signed out → login

    page = clients["s2@alpha"][0].get("/dashboard").get_data(as_text=True)
    assert url in page


def test_too_many_photos_rejected_before_anything_is_stored(world, app):
    _, _, clients = world
    before = len(get_storage().objects)
    resp = report(clients["s1@alpha"], files=[png_bytes()] * (app.config["MAX_PHOTOS_PER_ITEM"] + 1))
    assert resp.status_code == 400 and "up to" in resp.get_json()["error"]
    assert len(get_storage().objects) == before and Item.query.count() == 0


def test_removed_item_photo_hidden_from_students(world):
    _, _, clients = world
    item = db.session.get(Item, report(clients["s1@alpha"], files=[png_bytes()]).get_json()["id"])
    image_id = item.images[0].id
    assert post_json(clients["admin@alpha"], f"/api/item/delete/{item.id}").status_code == 200
    assert clients["s2@alpha"][0].get(f"/media/item-image/{image_id}").status_code == 404
    assert clients["admin@alpha"][0].get(f"/media/item-image/{image_id}").status_code == 200


def test_legacy_inline_photos_move_to_storage(world, app):
    college, _, _ = world
    jpeg = io.BytesIO()
    from PIL import Image
    Image.new("RGB", (10, 10)).save(jpeg, format="JPEG")
    legacy = make_item(college, name="Old", image_data="data:image/jpeg;base64," + base64.b64encode(jpeg.getvalue()).decode())
    broken = make_item(college, name="Broken", image_data="data:image/jpeg;base64,@@@not-base64")
    legacy_id, broken_id = legacy.id, broken.id
    out = app.test_cli_runner().invoke(args=["storage", "move-legacy-photos"])
    assert out.exit_code == 0, out.output
    assert "Moved 1 photo(s); skipped 1." in out.output
    legacy, broken = db.session.get(Item, legacy_id), db.session.get(Item, broken_id)
    assert legacy.image_data is None and len(legacy.images) == 1
    assert get_storage().get(legacy.images[0].storage_key) == jpeg.getvalue()
    assert broken.image_data is not None and not broken.images
    # Re-running is safe
    assert "Moved 0 photo(s); skipped 1." in app.test_cli_runner().invoke(args=["storage", "move-legacy-photos"]).output


def test_database_backend_keeps_2_0_behaviour(world, app):
    _, _, clients = world
    store = app.extensions.pop("photo_storage")
    app.config["STORAGE_BACKEND"] = "database"
    try:
        resp = report(clients["s1@alpha"], files=[png_bytes()])
        item = db.session.get(Item, resp.get_json()["id"])
        assert item.image_data.startswith("data:image/jpeg;base64,") and not item.images
    finally:
        app.config["STORAGE_BACKEND"] = "memory"
        app.extensions["photo_storage"] = store


def test_r2_backend_against_s3_api(app):
    """R2 speaks the S3 API. Run the real boto3 code against a local S3 server (moto)."""
    moto_server = pytest.importorskip("moto.server")
    import boto3
    import requests

    server = moto_server.ThreadedMotoServer(ip_address="127.0.0.1", port=0)
    server.start()
    try:
        host, port = server.get_host_and_port()
        endpoint = f"http://{host}:{port}"
        boto3.client("s3", endpoint_url=endpoint, region_name="us-east-1", aws_access_key_id="k",
                     aws_secret_access_key="s").create_bucket(Bucket="photos")
        from campus_retain.services.storage import R2Storage
        cfg = {"R2_ENDPOINT_URL": endpoint, "R2_BUCKET": "photos", "R2_ACCESS_KEY_ID": "k",
               "R2_SECRET_ACCESS_KEY": "s", "MEDIA_URL_TTL_SECONDS": 300}
        store = R2Storage(cfg)
        store.put("colleges/1/items/a.jpg", b"jpeg-bytes", "image/jpeg")
        assert store.get("colleges/1/items/a.jpg") == b"jpeg-bytes"
        signed = store.signed_url("colleges/1/items/a.jpg")
        assert "X-Amz-Signature=" in signed and "X-Amz-Expires=300" in signed
        fetched = requests.get(signed, timeout=10)
        assert fetched.status_code == 200 and fetched.content == b"jpeg-bytes"
        store.delete("colleges/1/items/a.jpg")
        with pytest.raises(Exception):
            store.get("colleges/1/items/a.jpg")
    finally:
        server.stop()


def test_r2_config_is_validated(monkeypatch):
    with pytest.raises(ConfigError, match="R2_ACCESS_KEY_ID"):
        load_config("test", {"STORAGE_BACKEND": "r2", "R2_BUCKET": "b", "R2_ACCOUNT_ID": "acc"})
    ok = load_config("test", {"STORAGE_BACKEND": "r2", "R2_BUCKET": "b", "R2_ACCOUNT_ID": "acc",
                              "R2_ACCESS_KEY_ID": "k", "R2_SECRET_ACCESS_KEY": "s"})
    assert ok["STORAGE_BACKEND"] == "r2"
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    monkeypatch.setenv("DATABASE_URL", "postgresql:///x")
    with pytest.raises(ConfigError, match="production"):
        load_config("production", {"STORAGE_BACKEND": "local"})


# ---------------------------------------------------------------- collection points

def test_admin_manages_collection_points_students_cannot(world):
    college, _, clients = world
    page = clients["admin@alpha"][0].get("/admin/collection-points")
    assert page.status_code == 200
    resp = form_post(clients["admin@alpha"], "/admin/collection-points", name="Main gate cabin",
                     opening_hours="9 am – 5 pm")
    assert resp.status_code == 302
    point = CollectionPoint.query.one()
    assert point.college_id == college.id and point.is_active
    form_post(clients["admin@alpha"], "/admin/collection-points", name="main gate cabin")
    assert CollectionPoint.query.count() == 1                           # duplicate name refused
    assert clients["s1@alpha"][0].get("/admin/collection-points").status_code == 403
    assert form_post(clients["s1@alpha"], "/admin/collection-points", name="X").status_code == 403
    assert form_post(clients["guard@beta"], f"/admin/collection-points/{point.id}/toggle").status_code == 403
    form_post(clients["admin@alpha"], f"/admin/collection-points/{point.id}/toggle")
    assert db.session.get(CollectionPoint, point.id).is_active is False


def test_report_with_collection_point_and_pickup_text(world, outbox):
    college, other, clients = world
    mine = CollectionPoint(college_id=college.id, name="Security cabin", opening_hours="9–5")
    theirs = CollectionPoint(college_id=other.id, name="Beta desk")
    db.session.add_all([mine, theirs])
    db.session.commit()
    assert report(clients["s1@alpha"], collection_point_id=theirs.id).status_code == 400
    resp = report(clients["s1@alpha"], collection_point_id=mine.id)
    item = db.session.get(Item, resp.get_json()["id"])
    assert item.collection_point_id == mine.id

    post_json(clients["s2@alpha"], "/api/claim", item_id=item.id, student_id="21CS2", proof_description="dent")
    outbox.clear()
    assert post_json(clients["admin@alpha"], f"/api/admin/approve/{item.id}").status_code == 200
    mail = next(m for m in outbox if m["to"] == "s2@alpha.edu.in")
    assert "Collect it from Security cabin, open 9–5." in mail["body"]

    # staff can move it; foreign collection point refused
    assert post_json(clients["admin@alpha"], f"/api/item/{item.id}/collection-point",
                     collection_point_id=theirs.id).status_code == 400
    assert post_json(clients["admin@alpha"], f"/api/item/{item.id}/collection-point",
                     collection_point_id=None).status_code == 200
    assert post_json(clients["s1@alpha"], f"/api/item/{item.id}/collection-point",
                     collection_point_id=mine.id).status_code == 403


# ---------------------------------------------------------------- pickup codes

@pytest.fixture
def approved(world, outbox):
    college, _, clients = world
    item = make_item(college)
    post_json(clients["s2@alpha"], "/api/claim", item_id=item.id, student_id="21CS2", proof_description="dent")
    post_json(clients["admin@alpha"], f"/api/admin/approve/{item.id}")
    claim = Claim.query.filter_by(item_id=item.id).one()
    return item, claim, last_code(outbox, "s2@alpha.edu.in")


def desk_verify(client_token, claim_id, code):
    return form_post(client_token, f"/desk/verify/{claim_id}", code=code)


def test_pickup_code_is_emailed_and_only_its_hash_stored(approved):
    item, claim, code = approved
    assert claim.status == ClaimStatus.APPROVED and claim.pickup_code_hash
    assert code not in claim.pickup_code_hash and claim.pickup_code_expires_at > claim.pickup_code_sent_at


def test_security_staff_hands_over_with_correct_code(world, approved, outbox):
    _, _, clients = world
    item, claim, code = approved
    page = clients["guard@alpha"][0].get("/desk/").get_data(as_text=True)
    assert item.name in page and "s2@alpha.edu.in" in page
    resp = desk_verify(clients["guard@alpha"], claim.id, code)
    assert resp.status_code == 302
    claim, item = db.session.get(Claim, claim.id), db.session.get(Item, item.id)
    assert claim.status == ClaimStatus.COLLECTED and item.status == ItemStatus.RETURNED
    assert claim.collected_by.email == "guard@alpha.edu.in" and claim.pickup_code_hash is None
    assert AuditLog.query.filter_by(action="pickup.collected").count() == 1
    assert any(m["to"] == "s2@alpha.edu.in" and "collected" in m["body"] for m in outbox)
    # the code can't be used twice
    desk_verify(clients["guard@alpha"], claim.id, code)
    assert db.session.get(Claim, claim.id).status == ClaimStatus.COLLECTED


def test_wrong_codes_lock_until_student_sends_a_new_one(world, approved, outbox, app):
    _, _, clients = world
    item, claim, code = approved
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(app.config["PICKUP_CODE_MAX_ATTEMPTS"]):
        desk_verify(clients["guard@alpha"], claim.id, wrong)
    desk_verify(clients["guard@alpha"], claim.id, code)                # right code, but locked
    claim = db.session.get(Claim, claim.id)
    assert claim.status == ClaimStatus.APPROVED and claim.pickup_code_attempts == app.config["PICKUP_CODE_MAX_ATTEMPTS"]

    # student requests a new code; old one stops working
    claim.pickup_code_sent_at = claim.pickup_code_sent_at.replace(year=2000)   # skip the resend wait
    db.session.commit()
    outbox.clear()
    assert form_post(clients["s2@alpha"], f"/me/claims/{claim.id}/pickup-code").status_code == 302
    new = last_code(outbox, "s2@alpha.edu.in")
    # immediate second request is throttled
    form_post(clients["s2@alpha"], f"/me/claims/{claim.id}/pickup-code")
    assert len([m for m in outbox if m["to"] == "s2@alpha.edu.in"]) == 1
    if new != code:
        desk_verify(clients["guard@alpha"], claim.id, code)
        assert db.session.get(Claim, claim.id).status == ClaimStatus.APPROVED
    desk_verify(clients["guard@alpha"], claim.id, new)
    assert db.session.get(Claim, claim.id).status == ClaimStatus.COLLECTED


def test_expired_code_rejected(world, approved):
    _, _, clients = world
    _, claim, code = approved
    claim.pickup_code_expires_at = claim.pickup_code_expires_at.replace(year=2000)
    db.session.commit()
    desk_verify(clients["guard@alpha"], claim.id, code)
    assert db.session.get(Claim, claim.id).status == ClaimStatus.APPROVED


def test_desk_is_staff_only_and_college_scoped(world, approved):
    _, _, clients = world
    _, claim, code = approved
    assert clients["s1@alpha"][0].get("/desk/").status_code == 403
    assert desk_verify(clients["s2@alpha"], claim.id, code).status_code == 403   # claimant can't self-serve
    desk_verify(clients["guard@beta"], claim.id, code)                          # other college
    assert db.session.get(Claim, claim.id).status == ClaimStatus.APPROVED
    assert claim.item.name not in clients["guard@beta"][0].get("/desk/").get_data(as_text=True)
    # someone else can't ask for a new code for this claim
    assert form_post(clients["s1@alpha"], f"/me/claims/{claim.id}/pickup-code").status_code == 302
    assert db.session.get(Claim, claim.id).pickup_code_attempts == 0


def test_campus_bound_guard_only_sees_own_campus(world, new_client, outbox):
    college, _, clients = world
    north, south = make_campus(college, "North"), make_campus(college, "South")
    make_user("northguard@alpha.edu.in", college, role="security_staff", campus=north)
    guard = new_client()
    login(guard, "northguard@alpha.edu.in")
    gt = (guard, api_token(guard))
    item = make_item(college, name="South laptop", campus=south)
    post_json(clients["s2@alpha"], "/api/claim", item_id=item.id, student_id="1", proof_description="x")
    post_json(clients["admin@alpha"], f"/api/admin/approve/{item.id}")
    code = last_code(outbox, "s2@alpha.edu.in")
    claim = Claim.query.filter_by(item_id=item.id).one()
    assert "South laptop" not in guard.get("/desk/").get_data(as_text=True)
    desk_verify(gt, claim.id, code)
    assert db.session.get(Claim, claim.id).status == ClaimStatus.APPROVED


def test_student_withdraws_pending_claim(world):
    college, _, clients = world
    item = make_item(college)
    post_json(clients["s2@alpha"], "/api/claim", item_id=item.id, student_id="1", proof_description="x")
    claim = Claim.query.one()
    assert form_post(clients["s1@alpha"], f"/me/claims/{claim.id}/withdraw").status_code == 404
    form_post(clients["s2@alpha"], f"/me/claims/{claim.id}/withdraw")
    assert db.session.get(Claim, claim.id).status == ClaimStatus.WITHDRAWN
    assert db.session.get(Item, item.id).status == ItemStatus.AVAILABLE


# ---------------------------------------------------------------- lost items

def test_lost_report_board_and_found_match_notifies_owner(world, outbox):
    _, _, clients = world
    resp = report(clients["s1@alpha"], kind="lost", name="Grey hoodie", location="Gym",
                  secret_detail="should be ignored")
    lost = db.session.get(Item, resp.get_json()["id"])
    assert lost.kind == ItemKind.LOST and lost.secret_detail is None

    found_page = clients["s2@alpha"][0].get("/dashboard").get_data(as_text=True)
    lost_page = clients["s2@alpha"][0].get("/dashboard?view=lost").get_data(as_text=True)
    assert "Grey hoodie" not in found_page and "Grey hoodie" in lost_page and "I found this" in lost_page
    assert "Grey hoodie" not in clients["s9@beta"][0].get("/dashboard?view=lost").get_data(as_text=True)

    # lost items can't be claimed
    assert post_json(clients["s2@alpha"], "/api/claim", item_id=lost.id, student_id="1",
                     proof_description="x").status_code == 409

    outbox.clear()
    resp = report(clients["s2@alpha"], name="Grey hoodie", location="Gym bench", lost_item_id=lost.id)
    assert resp.status_code == 200
    note = Notification.query.filter_by(kind="lost.possible_match").one()
    assert note.user_id == lost.reported_by_id
    assert any(m["to"] == "s1@alpha.edu.in" and "may be yours" in m["body"] for m in outbox)

    # can't "find" your own report, or another college's
    assert report(clients["s1@alpha"], lost_item_id=lost.id).status_code == 409
    assert report(clients["s9@beta"], lost_item_id=lost.id).status_code == 404


def test_owner_closes_lost_report(world):
    _, _, clients = world
    lost_id = report(clients["s1@alpha"], kind="lost", name="Umbrella").get_json()["id"]
    form_post(clients["s2@alpha"], f"/me/lost/{lost_id}/found")              # not the owner
    assert db.session.get(Item, lost_id).status == ItemStatus.AVAILABLE
    form_post(clients["s1@alpha"], f"/me/lost/{lost_id}/found")
    assert db.session.get(Item, lost_id).status == ItemStatus.RETURNED
    assert "Umbrella" not in clients["s2@alpha"][0].get("/dashboard?view=lost").get_data(as_text=True)


def test_activity_page_shows_claims_reports_and_marks_notifications_read(world, approved):
    _, _, clients = world
    item, claim, _ = approved
    page = clients["s2@alpha"][0].get("/me")
    html = page.get_data(as_text=True)
    assert page.status_code == 200 and item.name in html and "Email a new pickup code" in html
    assert "Claim approved" in html
    from campus_retain.models import User
    s2 = User.query.filter_by(email="s2@alpha.edu.in").one()
    assert Notification.query.filter_by(user_id=s2.id, read_at=None).count() == 0
    assert clients["s9@beta"][0].get("/me").get_data(as_text=True).count(item.name) == 0
