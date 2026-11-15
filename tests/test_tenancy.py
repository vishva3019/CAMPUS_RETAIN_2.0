"""College data isolation and role-based access."""
from campus_retain.extensions import db
from campus_retain.models import CollegeStatus, ItemStatus

from .conftest import api_token, login, make_campus, make_college, make_item, make_user


def setup_two_colleges():
    a = make_college("alpha", ("alpha.edu.in",))
    b = make_college("beta", ("beta.edu.in",))
    return a, b


def test_students_only_see_their_own_college(client):
    a, b = setup_two_colleges()
    make_user("s@alpha.edu.in", a)
    make_item(a, "Alpha umbrella")
    make_item(b, "Beta laptop")
    login(client, "s@alpha.edu.in")
    html = client.get("/dashboard").get_data(as_text=True)
    assert "Alpha umbrella" in html and "Beta laptop" not in html
    # Search can't reach across colleges either
    assert "Beta laptop" not in client.get("/dashboard?q=laptop").get_data(as_text=True)


def test_student_cannot_claim_other_college_item_by_id(client):
    a, b = setup_two_colleges()
    make_user("s@alpha.edu.in", a)
    foreign = make_item(b, "Beta laptop")
    login(client, "s@alpha.edu.in")
    resp = client.post("/api/claim", headers={"X-CSRFToken": api_token(client)},
                       json={"item_id": foreign.id, "student_id": "1", "proof_description": "mine"})
    assert resp.status_code == 404
    db.session.refresh(foreign)
    assert foreign.status == ItemStatus.AVAILABLE and foreign.claims == []


def test_admin_cannot_act_on_other_college(client):
    a, b = setup_two_colleges()
    make_user("admin@alpha.edu.in", a, role="college_admin")
    foreign = make_item(b, "Beta laptop", status=ItemStatus.PENDING)
    login(client, "admin@alpha.edu.in")
    token = api_token(client)
    for path in (f"/api/admin/approve/{foreign.id}", f"/api/admin/reject/{foreign.id}", f"/api/item/delete/{foreign.id}"):
        assert client.post(path, headers={"X-CSRFToken": token}, json={}).status_code == 404
    assert "Beta laptop" not in client.get("/admin").get_data(as_text=True)
    db.session.refresh(foreign)
    assert foreign.status == ItemStatus.PENDING


def test_report_ignores_browser_supplied_college(client):
    a, b = setup_two_colleges()
    make_user("s@alpha.edu.in", a)
    login(client, "s@alpha.edu.in")
    resp = client.post("/api/report", headers={"X-CSRFToken": api_token(client)},
                       data={"name": "Keys", "location": "Gate", "college_id": b.id})
    assert resp.status_code == 200
    from campus_retain.models import Item
    assert Item.query.one().college_id == a.id


def test_campus_moderator_is_limited_to_their_campus(client):
    a = make_college("alpha", ("alpha.edu.in",))
    north, south = make_campus(a, "North"), make_campus(a, "South")
    make_user("mod@alpha.edu.in", a, role="campus_moderator", campus=north)
    make_item(a, "North bottle", campus=north)
    south_item = make_item(a, "South bag", campus=south, status=ItemStatus.PENDING)
    login(client, "mod@alpha.edu.in")
    html = client.get("/admin").get_data(as_text=True)
    assert "North bottle" in html and "South bag" not in html
    resp = client.post(f"/api/admin/approve/{south_item.id}", headers={"X-CSRFToken": api_token(client)}, json={})
    assert resp.status_code == 404


def test_role_permissions_are_enforced_server_side(client, new_client):
    a = make_college()
    make_user("s@alpha.edu.in", a)
    make_user("guard@alpha.edu.in", a, role="security_staff")
    item = make_item(a, status=ItemStatus.PENDING)

    login(client, "s@alpha.edu.in")
    token = api_token(client)
    assert client.get("/admin").status_code == 403
    assert client.post(f"/api/admin/approve/{item.id}", headers={"X-CSRFToken": token}, json={}).status_code == 403
    assert client.post(f"/api/item/delete/{item.id}", headers={"X-CSRFToken": token}, json={}).status_code == 403
    assert client.get("/platform/").status_code == 403

    guard = new_client()
    login(guard, "guard@alpha.edu.in")
    gtoken = api_token(guard)
    assert guard.get("/admin").status_code == 200       # can view to verify pickups
    assert guard.post(f"/api/admin/approve/{item.id}", headers={"X-CSRFToken": gtoken}, json={}).status_code == 403
    assert guard.post("/api/report", headers={"X-CSRFToken": gtoken}, data={"name": "x", "location": "y"}).status_code == 403


def test_platform_admin_has_no_college_data_access(client):
    a = make_college()
    make_item(a, "Alpha umbrella")
    make_user("root@platform.test", None, role="platform_super_admin")
    resp = login(client, "root@platform.test")
    assert resp.location.endswith("/platform/")
    assert client.get("/dashboard").status_code == 403
    assert client.get("/admin").status_code == 403
    assert client.post("/api/claim", headers={"X-CSRFToken": api_token(client)}, json={}).status_code == 403


def test_suspending_a_college_signs_its_users_out(client):
    a = make_college()
    make_user("s@alpha.edu.in", a)
    login(client, "s@alpha.edu.in")
    assert client.get("/dashboard").status_code == 200
    a.status = CollegeStatus.SUSPENDED
    db.session.commit()
    assert client.get("/dashboard").status_code == 302
    assert login(client, "s@alpha.edu.in").status_code == 403


def test_unauthenticated_api_returns_401(client):
    make_college()
    from .conftest import get_csrf
    token = get_csrf(client)
    assert client.post("/api/claim", headers={"X-CSRFToken": token}, json={}).status_code == 401
    assert client.get("/dashboard").status_code == 302
