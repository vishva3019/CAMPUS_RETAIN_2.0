"""Animated onboarding: college-bound sign-up, email codes, sign-in and reset (/api/v1/auth)."""
import re
from datetime import timedelta

import pytest

from campus_retain.extensions import db
from campus_retain.models import AuditLog, College, EmailCode, PendingRegistration, User, utcnow

from .conftest import PASSWORD, make_college, make_user

GOOD_PASSWORD = "Blue-Kettle-Orbit-73"

COLLEGES = [
    ("alliance", "Alliance University", "ced.alliance.edu.in"),
    ("mvj-ce", "MVJ College of Engineering", "mvjce.edu.in"),
    ("vemana-it", "Vemana Institute of Technology", "vemanait.edu.in"),
]


@pytest.fixture
def colleges():
    out = {}
    for slug, name, domain in COLLEGES:
        c = make_college(slug=slug, domains=(domain,), name=name)
        c.listed_on_signup = True
        out[slug] = c
    db.session.commit()
    return out


def boot(client):
    data = client.get("/api/v1/auth/bootstrap").get_json()
    return data, {"X-CSRFToken": data["csrf_token"]}


def post(client, url, body=None, headers=None):
    if headers is None:
        headers = boot(client)[1]
    return client.post(url, json=body or {}, headers=headers)


def form(college, email, **kw):
    data = {"college_id": college.id, "full_name": "Asha Rao", "email": email, "student_id": "1AB22CS001",
            "department": "Computer Science and Engineering", "year_of_study": "3",
            "password": GOOD_PASSWORD, "confirm_password": GOOD_PASSWORD}
    data.update(kw)
    return data


def last_code(outbox, email):
    for mail in reversed(outbox):
        if mail["to"] == email:
            m = re.search(r"\b(\d{6})\b", mail["body"])
            if m:
                return m.group(1)
    raise AssertionError(f"no code mailed to {email}")


def fresh(obj_type, **filters):
    db.session.expire_all()
    return obj_type.query.filter_by(**filters).first()


# ---------------------------------------------------------------- the three colleges

@pytest.mark.parametrize("slug,local", [("alliance", "asha"), ("mvj-ce", "ravi"), ("vemana-it", "meera")])
def test_each_college_registers_with_its_own_domain(colleges, client, outbox, slug, local):
    college = colleges[slug]
    email = f"{local}@{college.domains[0].domain}"
    _, h = boot(client)
    resp = post(client, "/api/v1/auth/register", form(college, email.upper(), student_id=f"{slug[:3]}22cs1"), h)
    assert resp.status_code == 200 and resp.get_json()["status"] == "code_sent"
    assert resp.get_json()["email"] == email                       # normalised
    assert fresh(User, email=email) is None                         # no account before the code
    assert fresh(PendingRegistration, email=email).college_id == college.id
    code = last_code(outbox, email)
    assert code not in resp.get_data(as_text=True)                  # never in a response

    done = post(client, "/api/v1/auth/register/verify", {"otp": code}, h)
    assert done.status_code == 200, done.get_json()
    body = done.get_json()
    assert body["status"] == "signed_in" and body["college"]["name"] == college.name
    user = fresh(User, email=email)
    assert user.college_id == college.id and user.is_verified and user.role_name == "student"
    assert user.full_name == "Asha Rao" and user.student_id == f"{slug[:3]}22CS1".upper()
    assert user.department_name == "Computer Science and Engineering" and user.year_of_study == "3"
    assert user.password != GOOD_PASSWORD
    assert fresh(PendingRegistration, email=email) is None
    session = client.get("/api/v1/session").get_json()             # signed in to *that* college
    assert session["college"]["id"] == college.id and session["user"]["email"] == email


def test_bootstrap_lists_only_listed_active_colleges(colleges, client):
    make_college(slug="hidden", domains=("hidden.edu.in",))          # active but not listed
    data, _ = boot(client)
    assert [c["slug"] for c in data["colleges"]] == ["alliance", "mvj-ce", "vemana-it"]
    assert data["colleges"][0]["domains"] == ["ced.alliance.edu.in"]
    assert data["signed_in"] is False and data["code"]["length"] == 6


# ---------------------------------------------------------------- domain rules

@pytest.mark.parametrize("college_slug,email", [
    ("alliance", "student@gmail.com"),
    ("alliance", "student@mvjce.edu.in"),
    ("mvj-ce", "student@ced.alliance.edu.in"),
    ("alliance", "student@vemanait.edu.in"),
    ("vemana-it", "student@cse.vemanait.edu.in"),                   # subdomains don't count here
    ("alliance", "student@ced.alliance.edu.in.evil.com"),
    ("mvj-ce", "a b@mvjce.edu.in"),
])
def test_wrong_domain_is_rejected(colleges, client, outbox, college_slug, email):
    college = colleges[college_slug]
    resp = post(client, "/api/v1/auth/register", form(college, email))
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["field"] == "email"
    if " " not in email:
        assert body["error"] == (f"Please enter your official {college.name} email address ending with "
                                 f"@{college.domains[0].domain}.")
    assert outbox == [] and PendingRegistration.query.count() == 0


def test_direct_api_cannot_pick_unlisted_inactive_or_unknown_college(colleges, client):
    pending = make_college(slug="pend", domains=("pend.edu.in",), status="pending")
    pending.listed_on_signup = True
    unlisted = make_college(slug="unl", domains=("unl.edu.in",))
    db.session.commit()
    for cid, email in ((pending.id, "a@pend.edu.in"), (unlisted.id, "a@unl.edu.in"), (99999, "a@x.edu.in"), ("abc", "a@x.edu.in")):
        resp = post(client, "/api/v1/auth/register", form(College(id=0), email, college_id=cid))
        assert resp.status_code == 400 and resp.get_json()["field"] == "college"


def test_csrf_is_required(colleges, client):
    client.get("/api/v1/auth/bootstrap")
    resp = client.post("/api/v1/auth/register", json=form(colleges["alliance"], "a@ced.alliance.edu.in"))
    assert resp.status_code == 400 and PendingRegistration.query.count() == 0


@pytest.mark.parametrize("field,value", [
    ("full_name", "A"), ("full_name", "<script>"), ("student_id", "!!"), ("department", ""),
    ("year_of_study", "5"), ("password", "short"), ("password", "password123"),
    ("confirm_password", "different-but-long"),
])
def test_field_validation(colleges, client, field, value):
    data = form(colleges["alliance"], "asha@ced.alliance.edu.in", **{field: value})
    if field == "password":
        data["confirm_password"] = value
    resp = post(client, "/api/v1/auth/register", data)
    assert resp.status_code == 400 and resp.get_json()["field"] == field


def test_password_may_not_contain_email_or_usn(colleges, client):
    data = form(colleges["alliance"], "ashwini@ced.alliance.edu.in", password="ashwini-2026!", confirm_password="ashwini-2026!")
    assert post(client, "/api/v1/auth/register", data).get_json()["field"] == "password"


# ---------------------------------------------------------------- duplicates, enumeration

def test_existing_email_gets_same_response_and_a_notice(colleges, client, outbox):
    college = colleges["mvj-ce"]
    make_user("taken@mvjce.edu.in", college)
    resp = post(client, "/api/v1/auth/register", form(college, "taken@mvjce.edu.in"))
    assert resp.status_code == 200 and resp.get_json()["status"] == "code_sent"   # same as a new email
    assert len(outbox) == 1 and "already have" in outbox[0]["subject"]
    assert not re.search(r"\b\d{6}\b", outbox[0]["body"])                          # no code issued
    assert PendingRegistration.query.count() == 0 and User.query.count() == 1
    post(client, "/api/v1/auth/register", form(college, "taken@mvjce.edu.in"))
    assert len(outbox) == 1                                                         # notice throttled


def test_duplicate_student_id_is_refused_at_verification(colleges, client, outbox, new_client):
    college = colleges["alliance"]
    make_user("first@ced.alliance.edu.in", college)
    db.session.expire_all()
    first = User.query.filter_by(email="first@ced.alliance.edu.in").first()
    first.student_id = "1AB22CS001"
    db.session.commit()
    c = new_client()
    _, h = boot(c)
    post(c, "/api/v1/auth/register", form(college, "second@ced.alliance.edu.in"), h)
    resp = post(c, "/api/v1/auth/register/verify", {"otp": last_code(outbox, "second@ced.alliance.edu.in")}, h)
    assert resp.status_code == 409 and "1AB22CS001" in resp.get_json()["error"]
    assert fresh(User, email="second@ced.alliance.edu.in") is None


def test_same_student_id_allowed_at_another_college(colleges, client, outbox):
    make_user("x@mvjce.edu.in", colleges["mvj-ce"])
    u = fresh(User, email="x@mvjce.edu.in")
    u.student_id = "1AB22CS001"
    db.session.commit()
    _, h = boot(client)
    post(client, "/api/v1/auth/register", form(colleges["alliance"], "y@ced.alliance.edu.in"), h)
    resp = post(client, "/api/v1/auth/register/verify", {"otp": last_code(outbox, "y@ced.alliance.edu.in")}, h)
    assert resp.status_code == 200


# ---------------------------------------------------------------- codes

def start(client, outbox, college, email):
    _, h = boot(client)
    assert post(client, "/api/v1/auth/register", form(college, email), h).status_code == 200
    return h


def test_invalid_code_then_lockout(colleges, client, outbox, app):
    email = "asha@ced.alliance.edu.in"
    h = start(client, outbox, colleges["alliance"], email)
    for _ in range(app.config["CODE_MAX_ATTEMPTS"]):
        resp = post(client, "/api/v1/auth/register/verify", {"otp": "000000"}, h)
        assert resp.status_code == 400 and resp.get_json()["expired"] is False
    resp = post(client, "/api/v1/auth/register/verify", {"otp": last_code(outbox, email)}, h)
    assert resp.status_code == 400 and resp.get_json()["expired"] is True        # must request a new code
    assert fresh(User, email=email) is None


def test_expired_code(colleges, client, outbox):
    email = "asha@ced.alliance.edu.in"
    h = start(client, outbox, colleges["alliance"], email)
    code = last_code(outbox, email)
    rec = fresh(EmailCode, email=email)
    rec.expires_at = utcnow() - timedelta(seconds=1)
    db.session.commit()
    resp = post(client, "/api/v1/auth/register/verify", {"otp": code}, h)
    assert resp.status_code == 400 and resp.get_json()["expired"] is True
    assert fresh(User, email=email) is None


def test_resend_cooldown_and_old_code_invalidated(colleges, client, outbox, app):
    email = "asha@ced.alliance.edu.in"
    h = start(client, outbox, colleges["alliance"], email)
    first = last_code(outbox, email)
    resp = post(client, "/api/v1/auth/resend", {}, h)
    assert resp.status_code == 429 and 0 < resp.get_json()["resend_in"] <= app.config["CODE_RESEND_SECONDS"]
    assert len(outbox) == 1
    rec = fresh(EmailCode, email=email)
    rec.created_at = utcnow() - timedelta(seconds=app.config["CODE_RESEND_SECONDS"] + 1)
    db.session.commit()
    assert post(client, "/api/v1/auth/resend", {}, h).status_code == 200
    second = last_code(outbox, email)
    assert EmailCode.query.filter_by(email=email).count() == 1                       # old one deleted
    if first != second:
        assert post(client, "/api/v1/auth/register/verify", {"otp": first}, h).status_code == 400
    assert post(client, "/api/v1/auth/register/verify", {"otp": second}, h).status_code == 200


def test_codes_are_stored_hashed(colleges, client, outbox):
    email = "asha@ced.alliance.edu.in"
    start(client, outbox, colleges["alliance"], email)
    rec = fresh(EmailCode, email=email)
    assert last_code(outbox, email) not in rec.code_hash


def test_verify_needs_the_same_browser_session(colleges, client, outbox, new_client):
    email = "asha@ced.alliance.edu.in"
    start(client, outbox, colleges["alliance"], email)
    other = new_client()
    resp = post(other, "/api/v1/auth/register/verify", {"otp": last_code(outbox, email)})
    assert resp.status_code == 410 and fresh(User, email=email) is None


def test_expired_pending_registration(colleges, client, outbox):
    email = "asha@ced.alliance.edu.in"
    h = start(client, outbox, colleges["alliance"], email)
    p = fresh(PendingRegistration, email=email)
    p.expires_at = utcnow() - timedelta(seconds=1)
    db.session.commit()
    resp = post(client, "/api/v1/auth/register/verify", {"otp": last_code(outbox, email)}, h)
    assert resp.status_code == 410 and resp.get_json()["restart"] is True


# ---------------------------------------------------------------- sign in

def registered(client, outbox, college, email):
    h = start(client, outbox, college, email)
    assert post(client, "/api/v1/auth/register/verify", {"otp": last_code(outbox, email)}, h).status_code == 200
    client.get("/logout")


def test_login_after_registration(colleges, client, outbox):
    college = colleges["vemana-it"]
    registered(client, outbox, college, "meera@vemanait.edu.in")
    resp = post(client, "/api/v1/auth/login", {"college_id": college.id, "email": "Meera@VemanaIT.edu.in", "password": GOOD_PASSWORD})
    assert resp.status_code == 200 and resp.get_json()["home"] == "/dashboard"     # React off in tests
    assert client.get("/api/v1/session").get_json()["college"]["slug"] == "vemana-it"


def test_cannot_switch_college_at_login(colleges, client, outbox):
    registered(client, outbox, colleges["alliance"], "asha@ced.alliance.edu.in")
    # Wrong college selected with the real email: domain rule.
    resp = post(client, "/api/v1/auth/login", {"college_id": colleges["mvj-ce"].id, "email": "asha@ced.alliance.edu.in", "password": GOOD_PASSWORD})
    assert resp.status_code == 400 and "MVJ College of Engineering" in resp.get_json()["error"]
    assert client.get("/api/v1/session").status_code == 401
    # A domain can belong to only one college, so an email can never be valid for two.
    from campus_retain.models import CollegeDomain
    assert CollegeDomain.__table__.c.domain.unique


def test_wrong_password_and_unknown_email_look_the_same(colleges, client, outbox):
    college = colleges["alliance"]
    registered(client, outbox, college, "asha@ced.alliance.edu.in")
    a = post(client, "/api/v1/auth/login", {"college_id": college.id, "email": "asha@ced.alliance.edu.in", "password": "nope-nope-nope"})
    b = post(client, "/api/v1/auth/login", {"college_id": college.id, "email": "nobody@ced.alliance.edu.in", "password": "nope-nope-nope"})
    assert a.status_code == b.status_code == 401 and a.get_json()["error"] == b.get_json()["error"]


def test_remember_me_sets_a_persistent_cookie_only_when_asked(colleges, client, outbox, new_client):
    college = colleges["alliance"]
    registered(client, outbox, college, "asha@ced.alliance.edu.in")
    creds = {"college_id": college.id, "email": "asha@ced.alliance.edu.in", "password": GOOD_PASSWORD}
    short = new_client()
    resp = post(short, "/api/v1/auth/login", creds)
    cookie = resp.headers.get("Set-Cookie", "")
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie and "Expires" not in cookie
    long = new_client()
    resp = post(long, "/api/v1/auth/login", {**creds, "remember": True})
    assert "Expires" in resp.headers.get("Set-Cookie", "")


def test_server_side_session_expiry(colleges, client, outbox):
    college = colleges["alliance"]
    registered(client, outbox, college, "asha@ced.alliance.edu.in")
    post(client, "/api/v1/auth/login", {"college_id": college.id, "email": "asha@ced.alliance.edu.in", "password": GOOD_PASSWORD})
    assert client.get("/api/v1/session").status_code == 200
    with client.session_transaction() as s:
        s["exp"] = 1
    assert client.get("/api/v1/session").status_code == 401


def test_unverified_legacy_account_confirms_email_at_sign_in(colleges, client, outbox):
    college = colleges["mvj-ce"]
    make_user("old@mvjce.edu.in", college, verified=False)
    _, h = boot(client)
    resp = post(client, "/api/v1/auth/login", {"college_id": college.id, "email": "old@mvjce.edu.in", "password": PASSWORD}, h)
    assert resp.get_json()["status"] == "code_sent" and resp.get_json()["purpose"] == "verify"
    assert client.get("/api/v1/session").status_code == 401
    resp = post(client, "/api/v1/auth/verify-email", {"otp": last_code(outbox, "old@mvjce.edu.in")}, h)
    assert resp.status_code == 200 and fresh(User, email="old@mvjce.edu.in").is_verified


def test_returning_user_is_sent_to_dashboard(colleges, client, outbox):
    registered(client, outbox, colleges["alliance"], "asha@ced.alliance.edu.in")
    post(client, "/api/v1/auth/login", {"college_id": colleges["alliance"].id, "email": "asha@ced.alliance.edu.in", "password": GOOD_PASSWORD})
    assert client.get("/").status_code == 302
    data, _ = boot(client)
    assert data["signed_in"] is True and data["home"]
    assert post(client, "/api/v1/auth/register", form(colleges["alliance"], "z@ced.alliance.edu.in")).status_code == 409


# ---------------------------------------------------------------- password reset

def test_forgot_password_flow(colleges, client, outbox):
    college = colleges["mvj-ce"]
    registered(client, outbox, college, "ravi@mvjce.edu.in")
    _, h = boot(client)
    resp = post(client, "/api/v1/auth/forgot", {"college_id": college.id, "email": "ravi@mvjce.edu.in"}, h)
    assert resp.get_json()["status"] == "code_sent"
    new = "Green-Lantern-Bridge-58"
    resp = post(client, "/api/v1/auth/reset", {"otp": last_code(outbox, "ravi@mvjce.edu.in"), "password": new, "confirm_password": new}, h)
    assert resp.status_code == 200
    ok = post(client, "/api/v1/auth/login", {"college_id": college.id, "email": "ravi@mvjce.edu.in", "password": new})
    assert ok.status_code == 200


def test_forgot_password_does_not_reveal_accounts(colleges, client, outbox):
    college = colleges["mvj-ce"]
    resp = post(client, "/api/v1/auth/forgot", {"college_id": college.id, "email": "ghost@mvjce.edu.in"})
    assert resp.status_code == 200 and resp.get_json()["status"] == "code_sent" and outbox == []


# ---------------------------------------------------------------- platform listing + CLI

def test_platform_admin_toggles_listing(colleges, client):
    from .conftest import login
    make_user("root@platform.test", None, role="platform_super_admin")
    login(client, "root@platform.test", path="/admin_login")
    _, h = boot(client)
    cid = colleges["mvj-ce"].id
    resp = client.post(f"/api/v1/platform/colleges/{cid}/signup-listing", json={"listed": False}, headers=h)
    assert resp.status_code == 200
    assert [c["slug"] for c in boot(client)[0]["colleges"]] == ["alliance", "vemana-it"]
    assert AuditLog.query.filter_by(action="college.signup_listing").count() == 1


def test_student_cannot_toggle_listing(colleges, client, outbox):
    registered(client, outbox, colleges["alliance"], "asha@ced.alliance.edu.in")
    post(client, "/api/v1/auth/login", {"college_id": colleges["alliance"].id, "email": "asha@ced.alliance.edu.in", "password": GOOD_PASSWORD})
    _, h = boot(client)
    assert client.post(f"/api/v1/platform/colleges/{colleges['alliance'].id}/signup-listing", json={"listed": False}, headers=h).status_code == 403


def test_college_onboard_command_is_idempotent(app):
    runner = app.test_cli_runner()
    args = ["college", "onboard", "--name", "MVJ College of Engineering", "--slug", "mvj-ce", "--domain", "mvjce.edu.in", "--color", "#b91c1c"]
    assert runner.invoke(args=args).exit_code == 0
    assert runner.invoke(args=args).exit_code == 0
    db.session.expire_all()
    assert College.query.filter_by(slug="mvj-ce").count() == 1
    c = College.query.filter_by(slug="mvj-ce").first()
    assert c.listed_on_signup and c.status == "active" and [d.domain for d in c.domains] == ["mvjce.edu.in"]
    clash = runner.invoke(args=["college", "onboard", "--name", "X", "--slug", "x", "--domain", "mvjce.edu.in"])
    assert clash.exit_code != 0 and "already belongs" in clash.output


def test_register_and_login_are_rate_limited():
    import os

    from campus_retain import create_app
    from campus_retain.extensions import limiter
    app = create_app("test", {"RATELIMIT_ENABLED": True, "REGISTER_RATE_LIMIT": "2 per minute",
                              "LOGIN_RATE_LIMIT": "2 per minute", "SQLALCHEMY_DATABASE_URI": os.environ["TEST_DATABASE_URL"]})
    try:
        with app.app_context():
            limiter.reset()
            c = app.test_client()
            h = {"X-CSRFToken": c.get("/api/v1/auth/bootstrap").get_json()["csrf_token"]}
            reg = [c.post("/api/v1/auth/register", json={"college_id": 0}, headers=h).status_code for _ in range(3)]
            log = [c.post("/api/v1/auth/login", json={"college_id": 0}, headers=h).status_code for _ in range(3)]
            assert reg == [400, 400, 429] and log == [400, 400, 429]
            db.session.remove()
    finally:
        limiter.enabled = False
