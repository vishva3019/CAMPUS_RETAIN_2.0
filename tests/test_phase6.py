"""Phase 6: inter-college network, events, QR item tags, approximate locations."""
from datetime import timedelta

import pytest

from campus_retain.extensions import db
from campus_retain.models import AuditLog, Claim, Event, Item, ItemStatus, ItemTag, Notification, utcnow

from .conftest import api_token, csrf_from, last_code, login, make_college, make_item, make_user


@pytest.fixture
def world(new_client):
    a = make_college(contact_email="lf@alpha.edu.in")
    b = make_college(slug="beta", domains=("beta.edu.in",), city="Bengaluru")
    c = make_college(slug="gamma", domains=("gamma.edu.in",))
    for email, col, role in [("s1@alpha.edu.in", a, "student"), ("admin@alpha.edu.in", a, "college_admin"),
                             ("guard@alpha.edu.in", a, "security_staff"),
                             ("s2@beta.edu.in", b, "student"), ("admin@beta.edu.in", b, "college_admin"),
                             ("s3@gamma.edu.in", c, "student")]:
        make_user(email, col, role=role)
    clients = {}
    for email in ("s1@alpha.edu.in", "admin@alpha.edu.in", "guard@alpha.edu.in", "s2@beta.edu.in",
                  "admin@beta.edu.in", "s3@gamma.edu.in"):
        cl = new_client()
        login(cl, email, path="/admin_login" if "admin" in email or "guard" in email else "/login")
        clients[email.split("@")[0] + "@" + email.split("@")[1].split(".")[0]] = (cl, api_token(cl))
    return a, b, c, clients


def post(ct, path, **body):
    r = ct[0].post(path, headers={"X-CSRFToken": ct[1]}, json=body)
    db.session.expire_all()
    return r


def join(ct):
    return post(ct, "/api/v1/admin/settings", inter_college_matching=True)


def test_network_is_opt_in_and_redacted(world):
    a, b, c, cl = world
    make_item(a, name="Laptop charger", secret_detail="SECRET-XYZ", location="Room 101", description="Dell 65W")
    assert cl["s2@beta"][0].get("/api/v1/network/items").get_json()["enabled"] is False
    assert cl["s2@beta"][0].post("/api/v1/admin/settings", headers={"X-CSRFToken": cl["s2@beta"][1]},
                                 json={"inter_college_matching": True}).status_code == 403   # students can't
    join(cl["admin@beta"])
    assert cl["s2@beta"][0].get("/api/v1/network/items").get_json()["total"] == 0          # alpha not opted in
    join(cl["admin@alpha"])
    data = cl["s2@beta"][0].get("/api/v1/network/items").get_json()
    assert data["total"] == 1 and data["items"][0]["college"] == a.name
    body = str(data)
    for private in ("SECRET-XYZ", "Room 101", "Dell 65W", "/media/"):
        assert private not in body
    assert cl["s3@gamma"][0].get("/api/v1/network/items").get_json()["enabled"] is False    # gamma not opted in
    assert cl["s1@alpha"][0].get("/api/v1/network/items").get_json()["total"] == 0          # own college excluded


def test_network_claim_is_reviewed_and_handed_over_by_item_college(world, outbox):
    a, b, _, cl = world
    item = make_item(a, name="Laptop charger")
    join(cl["admin@alpha"]); join(cl["admin@beta"])
    assert post(cl["s3@gamma"], "/api/v1/network/claims", item_id=item.id, student_id="9", proof_description="x").status_code == 403
    r = post(cl["s2@beta"], "/api/v1/network/claims", item_id=item.id, student_id="B42", proof_description="Dell sticker on the brick")
    assert r.status_code == 200
    claim = Claim.query.one()
    assert claim.college_id == a.id and claim.claimant.college_id == b.id
    assert AuditLog.query.filter_by(action="network.claim").count() == 1
    assert any(m["to"] == "lf@alpha.edu.in" for m in outbox)
    staff_view = cl["admin@alpha"][0].get("/api/v1/admin/items?status=pending").get_json()["items"][0]["claims"][0]
    assert staff_view["claimant_college"] == b.name
    assert cl["admin@beta"][0].get("/api/v1/admin/items?status=pending").get_json()["total"] == 0
    post(cl["admin@alpha"], f"/api/admin/approve/{item.id}")
    mine = cl["s2@beta"][0].get("/api/v1/me/activity").get_json()["claims"][0]
    assert mine["status"] == "approved" and mine["item"]["college"] == a.name and mine["item"]["photo"] is None
    code = last_code(outbox, "s2@beta.edu.in")
    assert post(cl["guard@alpha"], f"/api/v1/desk/{claim.id}/verify", code=code).status_code == 200
    assert db.session.get(Item, item.id).status == ItemStatus.RETURNED


def test_leaving_the_network_hides_listings(world):
    a, b, _, cl = world
    make_item(a)
    join(cl["admin@alpha"]); join(cl["admin@beta"])
    assert cl["s2@beta"][0].get("/api/v1/network/items").get_json()["total"] == 1
    post(cl["admin@alpha"], "/api/v1/admin/settings", inter_college_matching=False)
    assert cl["s2@beta"][0].get("/api/v1/network/items").get_json()["total"] == 0


def test_events(world):
    a, _, _, cl = world
    today = utcnow().date()
    r = post(cl["admin@alpha"], "/api/v1/admin/events", name="TechFest 2026",
             starts_on=today.isoformat(), ends_on=(today + timedelta(days=2)).isoformat())
    event = r.get_json()["event"]
    assert event["slug"] == "techfest-2026" and event["is_open"]
    assert post(cl["s1@alpha"], "/api/v1/admin/events", name="x", starts_on=today.isoformat(), ends_on=today.isoformat()).status_code == 403
    assert post(cl["admin@alpha"], "/api/v1/admin/events", name="Bad", starts_on="2026-02-02", ends_on="2026-01-01").status_code == 400
    c, t = cl["s1@alpha"]
    ok = c.post("/api/report", headers={"X-CSRFToken": t}, data={"name": "Cap", "location": "Main stage", "event_id": event["id"]})
    assert ok.status_code == 200
    items = c.get(f"/api/v1/items?event={event['id']}").get_json()["items"]
    assert [i["name"] for i in items] == ["Cap"] and items[0]["event"]["name"] == "TechFest 2026"
    old = Event(college_id=a.id, slug="old", name="Old fest", starts_at=utcnow() - timedelta(days=60), ends_at=utcnow() - timedelta(days=50))
    db.session.add(old); db.session.commit()
    assert c.post("/api/report", headers={"X-CSRFToken": t}, data={"name": "x", "location": "y", "event_id": old.id}).status_code == 400
    qr = c.get(f"/api/v1/events/{event['id']}/qr.svg")
    assert qr.status_code == 200 and qr.mimetype == "image/svg+xml" and b"<svg" in qr.data
    assert cl["s2@beta"][0].get(f"/api/v1/events/{event['id']}/qr.svg").status_code == 404


def test_qr_tag_lets_a_finder_message_the_owner_anonymously(world, client, outbox):
    _, _, _, cl = world
    tag = post(cl["s1@alpha"], "/api/v1/me/tags", label="Blue water bottle").get_json()["tag"]
    assert "/t/" in tag["url"]
    assert cl["s1@alpha"][0].get(f"/api/v1/me/tags/{tag['id']}/qr.svg").status_code == 200
    assert cl["s2@beta"][0].get(f"/api/v1/me/tags/{tag['id']}/qr.svg").status_code == 404
    page = client.get(f"/t/{tag['code']}")                               # no login needed
    html = page.get_data(as_text=True)
    assert page.status_code == 200 and "Blue water bottle" in html and "s1@alpha.edu.in" not in html
    token = csrf_from(html)
    assert client.post(f"/t/{tag['code']}", data={"csrf_token": token, "message": "hi"}).status_code == 400
    sent = client.post(f"/t/{tag['code']}", data={"csrf_token": token, "message": "Left it at the library desk", "contact": "98450 00000"})
    assert sent.status_code == 200 and "Thank you" in sent.get_data(as_text=True)
    mail = [m for m in outbox if m["to"] == "s1@alpha.edu.in"][-1]
    assert "Left it at the library desk" in mail["body"] and "98450 00000" in mail["body"]
    assert Notification.query.filter_by(kind="tag.found").count() == 1
    assert db.session.get(ItemTag, tag["id"]).scan_count == 1
    post(cl["s1@alpha"], f"/api/v1/me/tags/{tag['id']}/toggle")
    assert client.get(f"/t/{tag['code']}").status_code == 404
    assert client.get("/t/doesnotexist").status_code == 404


def test_location_is_rounded_and_mapped(world):
    _, _, _, cl = world
    c, t = cl["s1@alpha"]
    c.post("/api/report", headers={"X-CSRFToken": t}, data={"name": "Keys", "location": "Gate", "latitude": "12.971598", "longitude": "77.594566"})
    assert c.post("/api/report", headers={"X-CSRFToken": t}, data={"name": "x", "location": "y", "latitude": "200", "longitude": "1"}).status_code == 400
    item = Item.query.filter_by(name="Keys").one()
    assert float(item.latitude) == 12.972 and float(item.longitude) == 77.595
    pins = cl["s1@alpha"][0].get("/api/v1/map/items").get_json()["items"]
    assert pins == [{"id": item.id, "name": "Keys", "category": "Other", "location": "Gate", "status": "Available",
                     "lat": 12.972, "lng": 77.595, "reported_at": pins[0]["reported_at"]}]
    assert cl["s2@beta"][0].get("/api/v1/map/items").get_json()["items"] == []
