"""Platform console: onboarding a college end to end."""
from campus_retain.models import AuditLog, College, CollegeStatus, User

from .conftest import csrf_from, get_csrf, last_code, login, make_college, make_user


def test_onboard_college_activate_invite_admin(client, new_client, outbox):
    make_user("root@platform.test", None, role="platform_super_admin")
    login(client, "root@platform.test")
    token = csrf_from(client.get("/platform/").get_data(as_text=True))

    resp = client.post("/platform/colleges", data={
        "csrf_token": token, "name": "Gamma Institute", "slug": "gamma", "domains": "gamma.ac.in, @Students.Gamma.ac.in",
        "support_office": "Block C reception", "pickup_instructions": "Bring your ID to Block C."}, follow_redirects=True)
    assert "added as pending" in resp.get_data(as_text=True)
    college = College.query.filter_by(slug="gamma").one()
    assert college.status == CollegeStatus.PENDING
    assert sorted(d.domain for d in college.domains) == ["gamma.ac.in", "students.gamma.ac.in"]

    # Pending colleges can't take registrations
    student = new_client()
    t = get_csrf(student)
    assert student.post("/login", data={"email": "x@gamma.ac.in", "password": "p", "csrf_token": t}).status_code == 400

    client.post(f"/platform/colleges/{college.id}/status", data={"csrf_token": token, "status": "active"})
    client.post(f"/platform/colleges/{college.id}/admins", data={"csrf_token": token, "email": "head@gamma.ac.in"})
    admin = User.query.filter_by(email="head@gamma.ac.in").one()
    assert admin.role_name == "college_admin" and not admin.is_verified
    assert any(m["to"] == "head@gamma.ac.in" for m in outbox)

    # Invited admin sets a password through the reset flow, then reaches the admin dashboard
    a = new_client()
    t = get_csrf(a)
    a.post("/forgot-password", data={"email": "head@gamma.ac.in", "csrf_token": t})
    a.post("/verify-code", data={"otp": last_code(outbox, "head@gamma.ac.in"), "new_password": "gamma-admin-pass", "csrf_token": t})
    resp = login(a, "head@gamma.ac.in", "gamma-admin-pass")
    assert resp.location.endswith("/admin")
    assert "Gamma Institute" in a.get("/admin").get_data(as_text=True)

    actions = {x.action for x in AuditLog.query.all()}
    assert {"college.created", "college.status_changed", "user.invited"} <= actions


def test_duplicate_domain_and_bad_slug_rejected(client):
    make_college("alpha", ("alpha.edu.in",))
    make_user("root@platform.test", None, role="platform_super_admin")
    login(client, "root@platform.test")
    token = csrf_from(client.get("/platform/").get_data(as_text=True))
    resp = client.post("/platform/colleges", follow_redirects=True,
                       data={"csrf_token": token, "name": "Copy", "slug": "copy", "domains": "alpha.edu.in"})
    assert "Already registered" in resp.get_data(as_text=True)
    resp = client.post("/platform/colleges", follow_redirects=True,
                       data={"csrf_token": token, "name": "Bad", "slug": "Bad Slug!", "domains": "bad.edu.in"})
    assert "Slug must be" in resp.get_data(as_text=True)
    assert College.query.count() == 1


def test_college_admin_cannot_use_platform_console(client):
    college = make_college()
    make_user("admin@alpha.edu.in", college, role="college_admin")
    login(client, "admin@alpha.edu.in")
    assert client.get("/platform/").status_code == 403
