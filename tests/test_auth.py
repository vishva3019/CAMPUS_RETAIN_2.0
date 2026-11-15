"""Registration, verification, login protection and password recovery."""
import base64
import zlib
from datetime import timedelta

from campus_retain.extensions import db
from campus_retain.models import AuditLog, CollegeStatus, EmailCode, User, utcnow

from .conftest import (PASSWORD, get_csrf, last_code, login, make_campus, make_college,
                       make_user)


def start_signup(client, email, path="/login"):
    token = get_csrf(client, path)
    resp = client.post(path, data={"email": email, "password": "ignored", "csrf_token": token})
    return resp, token


def verify(client, token, code, password="new-password-123", **extra):
    return client.post("/verify-code", data={"otp": code, "new_password": password, "csrf_token": token, **extra})


def test_registration_requires_email_verification(client, outbox):
    college = make_college()
    resp, token = start_signup(client, "asha@alpha.edu.in")
    assert resp.status_code == 200 and "verification code" in resp.get_data(as_text=True)
    assert User.query.count() == 0, "no account may exist before the email is verified"

    resp = verify(client, token, last_code(outbox, "asha@alpha.edu.in"))
    assert resp.status_code == 302 and resp.location.endswith("/dashboard")
    user = User.query.filter_by(email="asha@alpha.edu.in").one()
    assert user.college_id == college.id and user.role_name == "student" and user.is_verified
    assert client.get("/dashboard").status_code == 200
    assert AuditLog.query.filter_by(action="auth.registered").count() == 1


def test_subdomain_maps_to_college_and_campus_is_saved(client, outbox):
    college = make_college(domains=("alpha.edu.in",))
    campus = make_campus(college, "North")
    _, token = start_signup(client, "ravi@cse.alpha.edu.in")
    verify(client, token, last_code(outbox), campus_id=campus.id)
    assert User.query.one().campus_id == campus.id


def test_campus_from_another_college_is_rejected(client, outbox):
    make_college("alpha", ("alpha.edu.in",))
    other_campus = make_campus(make_college("beta", ("beta.edu.in",)), "Beta Main")
    _, token = start_signup(client, "x@alpha.edu.in")
    resp = verify(client, token, last_code(outbox), campus_id=other_campus.id)
    assert resp.status_code == 400 and User.query.count() == 0


def test_unknown_and_inactive_domains_cannot_register(client, outbox):
    make_college("pend", ("pend.edu.in",), status=CollegeStatus.PENDING)
    make_college("susp", ("susp.edu.in",), status=CollegeStatus.SUSPENDED)
    for email in ("a@gmail.com", "b@pend.edu.in", "c@susp.edu.in"):
        resp, _ = start_signup(client, email)
        assert resp.status_code == 400
        assert "registered on Campus Retain" in resp.get_data(as_text=True)
    assert outbox == []


def test_branded_login_refuses_other_college_emails(client, outbox):
    make_college("alpha", ("alpha.edu.in",))
    make_college("beta", ("beta.edu.in",))
    resp, _ = start_signup(client, "z@beta.edu.in", path="/c/alpha/login")
    assert resp.status_code == 400 and outbox == []
    assert client.get("/c/does-not-exist/login").status_code == 404


def test_wrong_code_is_rejected_and_code_burns_after_max_attempts(client, outbox, app):
    make_college()
    _, token = start_signup(client, "asha@alpha.edu.in")
    real = last_code(outbox)
    wrong = "000000" if real != "000000" else "111111"
    for _ in range(app.config["CODE_MAX_ATTEMPTS"]):
        assert "not correct" in verify(client, token, wrong).get_data(as_text=True)
    resp = verify(client, token, real)
    assert "Too many wrong attempts" in resp.get_data(as_text=True)
    assert User.query.count() == 0 and EmailCode.query.count() == 0


def test_expired_code_is_rejected(client, outbox):
    make_college()
    _, token = start_signup(client, "asha@alpha.edu.in")
    EmailCode.query.update({EmailCode.expires_at: utcnow() - timedelta(seconds=1)})
    db.session.commit()
    assert "expired" in verify(client, token, last_code(outbox)).get_data(as_text=True)
    assert User.query.count() == 0


def test_codes_are_hashed_and_not_in_the_session_cookie(client, outbox):
    make_college()
    start_signup(client, "asha@alpha.edu.in")
    code = last_code(outbox)
    assert EmailCode.query.one().code_hash != code
    cookie = client.get_cookie("session").value
    payload = cookie.lstrip(".").split(".")[0]
    raw = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
    if cookie.startswith("."):
        raw = zlib.decompress(raw)
    assert code.encode() not in raw


def test_short_password_rejected(client, outbox):
    make_college()
    _, token = start_signup(client, "asha@alpha.edu.in")
    resp = verify(client, token, last_code(outbox), password="short")
    assert resp.status_code == 400 and User.query.count() == 0


def test_login_and_account_lockout(client, app):
    college = make_college()
    make_user("asha@alpha.edu.in", college)
    for _ in range(app.config["MAX_FAILED_LOGINS"]):
        assert login(client, "asha@alpha.edu.in", "wrong-password").status_code == 401
    resp = login(client, "asha@alpha.edu.in")  # correct password, but locked
    assert resp.status_code == 429 and "Too many failed attempts" in resp.get_data(as_text=True)

    User.query.update({User.locked_until: utcnow() - timedelta(seconds=1)})
    db.session.commit()
    resp = login(client, "asha@alpha.edu.in")
    assert resp.status_code == 302 and resp.location.endswith("/dashboard")


def test_unverified_legacy_user_must_confirm_email_once(client, outbox):
    college = make_college()
    make_user("old@alpha.edu.in", college, verified=False)
    resp = login(client, "old@alpha.edu.in")
    assert resp.status_code == 200 and "Confirm" in resp.get_data(as_text=True)
    assert client.get("/dashboard").status_code == 302  # not signed in yet
    token = get_csrf(client, "/login")
    resp = client.post("/verify-code", data={"otp": last_code(outbox), "csrf_token": token})
    assert resp.status_code == 302 and client.get("/dashboard").status_code == 200
    assert User.query.one().is_verified


def test_password_reset_signs_out_other_sessions(app, outbox, new_client):
    college = make_college()
    make_user("asha@alpha.edu.in", college)
    other_device = new_client()
    login(other_device, "asha@alpha.edu.in")
    assert other_device.get("/dashboard").status_code == 200

    c = new_client()
    token = get_csrf(c)
    c.post("/forgot-password", data={"email": "asha@alpha.edu.in", "csrf_token": token})
    resp = c.post("/verify-code", data={"otp": last_code(outbox), "new_password": "brand-new-pass-1", "csrf_token": token})
    assert "Password updated" in resp.get_data(as_text=True)

    assert other_device.get("/dashboard").status_code == 302, "old session must be invalidated"
    assert login(c, "asha@alpha.edu.in", PASSWORD).status_code == 401
    assert login(c, "asha@alpha.edu.in", "brand-new-pass-1").status_code == 302


def test_forgot_password_does_not_reveal_accounts(client, outbox):
    college = make_college()
    make_user("asha@alpha.edu.in", college)
    token = get_csrf(client)
    known = client.post("/forgot-password", data={"email": "asha@alpha.edu.in", "csrf_token": token})
    unknown = client.post("/forgot-password", data={"email": "nobody@alpha.edu.in", "csrf_token": token})
    assert known.status_code == unknown.status_code == 200
    assert "If an account exists" in known.get_data(as_text=True)
    assert "If an account exists" in unknown.get_data(as_text=True)
    assert [m["to"] for m in outbox] == ["asha@alpha.edu.in"]


def test_resend_is_throttled(client, outbox):
    make_college()
    _, token = start_signup(client, "asha@alpha.edu.in")
    client.post("/resend-code", data={"csrf_token": token})
    assert len(outbox) == 1
    EmailCode.query.update({EmailCode.created_at: utcnow() - timedelta(minutes=2)})
    db.session.commit()
    client.post("/resend-code", data={"csrf_token": token})
    assert len(outbox) == 2


def test_open_redirect_blocked(client):
    college = make_college()
    make_user("asha@alpha.edu.in", college)
    token = get_csrf(client)
    resp = client.post("/login?next=//evil.example/x", data={"email": "asha@alpha.edu.in", "password": PASSWORD, "csrf_token": token})
    assert resp.location.endswith("/dashboard")


def test_deactivated_user_cannot_log_in(client):
    college = make_college()
    user = make_user("asha@alpha.edu.in", college)
    user.is_active = False
    db.session.commit()
    assert login(client, "asha@alpha.edu.in").status_code == 401
