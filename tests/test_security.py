"""CSRF, headers, rate limiting, config safety, health and error handling."""
import pytest

from campus_retain import create_app
from campus_retain.config import ConfigError, load_config
from campus_retain.extensions import db

from .conftest import PASSWORD, api_token, login, make_college, make_item, make_user


def test_forms_and_api_require_csrf(client):
    college = make_college()
    make_user("s@alpha.edu.in", college)
    resp = client.post("/login", data={"email": "s@alpha.edu.in", "password": PASSWORD})
    assert resp.status_code == 400
    login(client, "s@alpha.edu.in")
    item = make_item(college)
    resp = client.post("/api/claim", json={"item_id": item.id, "student_id": "1", "proof_description": "p"})
    assert resp.status_code == 400 and "session expired" in resp.get_json()["error"]
    resp = client.post("/api/claim", headers={"X-CSRFToken": "forged"},
                       json={"item_id": item.id, "student_id": "1", "proof_description": "p"})
    assert resp.status_code == 400


def test_security_headers(client):
    resp = client.get("/login")
    h = resp.headers
    assert h["X-Content-Type-Options"] == "nosniff"
    assert h["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in h["Content-Security-Policy"]
    assert h["Referrer-Policy"]


def test_session_cookie_flags(app):
    assert app.config["SESSION_COOKIE_HTTPONLY"] and app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    prod = load_config("production", {"SECRET_KEY": "x" * 40, "SQLALCHEMY_DATABASE_URI": "postgresql:///x"})
    assert prod["SESSION_COOKIE_SECURE"] is True


def test_item_names_are_escaped(client):
    college = make_college()
    make_user("s@alpha.edu.in", college)
    make_item(college, name="Bag');alert(1);//<script>x</script>")
    login(client, "s@alpha.edu.in")
    html = client.get("/dashboard").get_data(as_text=True)
    assert "<script>x</script>" not in html
    assert "openClaimModal('" not in html  # names are only passed through data attributes


def test_production_refuses_missing_or_weak_secrets(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql:///x")
    with pytest.raises(ConfigError, match="SECRET_KEY"):
        load_config("production")
    monkeypatch.setenv("SECRET_KEY", "short")
    with pytest.raises(ConfigError, match="32 characters"):
        load_config("production")
    monkeypatch.setenv("SECRET_KEY", "k" * 40)
    monkeypatch.delenv("DATABASE_URL")
    with pytest.raises(ConfigError, match="DATABASE_URL"):
        load_config("production")


def test_removed_2_0_endpoints_are_gone(client):
    for path in ("/init-db", "/test-email", "/test-sms"):
        assert client.get(path).status_code == 404


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200 and resp.get_json() == {"status": "ok", "database": "ok"}


def test_api_errors_are_json_without_internals(client):
    resp = client.get("/api/nope")
    assert resp.status_code == 404 and resp.get_json() == {"error": "We couldn't find that page."}


def test_login_rate_limit():
    import os
    app = create_app("test", {"RATELIMIT_ENABLED": True, "LOGIN_RATE_LIMIT": "3 per minute",
                              "SQLALCHEMY_DATABASE_URI": os.environ["TEST_DATABASE_URL"]})
    from campus_retain.extensions import limiter
    try:
        with app.app_context():
            limiter.reset()
            c = app.test_client()
            from .conftest import get_csrf
            token = get_csrf(c)
            codes = [c.post("/login", data={"email": "a@nowhere.test", "password": "x", "csrf_token": token}).status_code
                     for _ in range(4)]
            assert codes[:3] == [400, 400, 400] and codes[3] == 429
            db.session.remove()
    finally:
        limiter.enabled = False  # the limiter object is shared; keep it off for the other tests


def test_maintenance_mode_blocks_students_not_staff(app, new_client):
    college = make_college()
    make_user("s@alpha.edu.in", college)
    make_user("admin@alpha.edu.in", college, role="college_admin")
    student, admin = new_client(), new_client()
    login(student, "s@alpha.edu.in")
    login(admin, "admin@alpha.edu.in")
    app.config["MAINTENANCE_MODE"] = True
    try:
        assert student.get("/dashboard").status_code == 503
        assert admin.get("/admin").status_code == 200
        assert student.get("/healthz").status_code == 200
    finally:
        app.config["MAINTENANCE_MODE"] = False


def test_logged_in_pages_are_not_cached(client):
    college = make_college()
    make_user("s@alpha.edu.in", college)
    login(client, "s@alpha.edu.in")
    assert client.get("/dashboard").headers["Cache-Control"] == "no-store"
    assert api_token(client)
