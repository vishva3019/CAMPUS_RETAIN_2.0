"""Phase 7: PostgreSQL row-level security, exercised as a restricted (non-superuser)
database role, the way production should connect. The rest of the suite runs as a
superuser, which PostgreSQL always lets through RLS."""
import pytest
from sqlalchemy import create_engine, text

from campus_retain import create_app
from campus_retain.extensions import db
from campus_retain.models import Claim

from .conftest import FreshContextClient, api_token, login, make_college, make_item, make_user

ROLE = "campus_retain_rls_test"


@pytest.fixture
def rls_app(app):
    url = app.config["SQLALCHEMY_DATABASE_URI"]
    with app.app_context():
        conn = db.session.connection()
        conn.execute(text(f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}') "
                          f"THEN CREATE ROLE {ROLE} LOGIN NOSUPERUSER NOBYPASSRLS; END IF; END $$"))
        conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {ROLE}"))
        conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {ROLE}"))
        conn.execute(text(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {ROLE}"))
        db.session.commit()
    # Same database, connecting as the restricted role
    from sqlalchemy.engine import make_url
    role_url = make_url(url).set(username=ROLE, password=None)
    restricted = create_app("test", overrides={"SQLALCHEMY_DATABASE_URI": role_url.render_as_string(hide_password=False)})
    restricted.test_client_class = FreshContextClient
    restricted.extensions["mail_outbox"] = []
    yield restricted
    with restricted.app_context():
        db.engine.dispose()


def test_policies_hide_other_colleges_rows_at_the_database(app, rls_app):
    a = make_college()
    b = make_college(slug="beta", domains=("beta.edu.in",))
    make_item(a, name="Alpha item")
    make_item(b, name="Beta item")
    engine = create_engine(rls_app.config["SQLALCHEMY_DATABASE_URI"])
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.college_id', :v, true)"), {"v": str(a.id)})
            names = [r[0] for r in conn.execute(text("SELECT name FROM item ORDER BY name"))]
            assert names == ["Alpha item"]
            with pytest.raises(Exception):     # WITH CHECK: can't write another college's rows
                conn.execute(text("INSERT INTO item (name, college_id, status, kind) VALUES ('x', :b, 'Available', 'found')"),
                             {"b": b.id})
        with engine.begin() as conn:            # no scope (CLI, platform admin): everything
            assert conn.execute(text("SELECT count(*) FROM item")).scalar() == 2
    finally:
        engine.dispose()


def test_app_works_under_rls_including_the_network(app, rls_app):
    a = make_college()
    b = make_college(slug="beta", domains=("beta.edu.in",))
    make_user("s1@alpha.edu.in", a)
    make_user("admin@alpha.edu.in", a, role="college_admin")
    make_user("s2@beta.edu.in", b)
    make_user("admin@beta.edu.in", b, role="college_admin")
    item = make_item(a, name="Alpha charger")
    make_item(b, name="Beta bottle")

    def client(email, path="/login"):
        c = rls_app.test_client()
        login(c, email, path=path)
        return c, api_token(c)

    s1, s2 = client("s1@alpha.edu.in"), client("s2@beta.edu.in")
    adm_a, adm_b = client("admin@alpha.edu.in", "/admin_login"), client("admin@beta.edu.in", "/admin_login")
    assert [i["name"] for i in s1[0].get("/api/v1/items").get_json()["items"]] == ["Alpha charger"]
    assert [i["name"] for i in s2[0].get("/api/v1/items").get_json()["items"]] == ["Beta bottle"]
    # report under RLS
    assert s1[0].post("/api/report", headers={"X-CSRFToken": s1[1]}, data={"name": "Cap", "location": "Gate"}).status_code == 200

    # network: deliberate cross-college read and claim still work
    for adm in (adm_a, adm_b):
        assert adm[0].post("/api/v1/admin/settings", headers={"X-CSRFToken": adm[1]}, json={"inter_college_matching": True}).status_code == 200
    listed = s2[0].get("/api/v1/network/items").get_json()
    assert "Alpha charger" in [i["name"] for i in listed["items"]]
    r = s2[0].post("/api/v1/network/claims", headers={"X-CSRFToken": s2[1]},
                   json={"item_id": item.id, "student_id": "B1", "proof_description": "my sticker"})
    assert r.status_code == 200, r.get_json()
    mine = s2[0].get("/api/v1/me/activity").get_json()["claims"]
    assert [c["item"]["name"] for c in mine] == ["Alpha charger"]
    staff = adm_a[0].get("/api/v1/admin/items?status=pending").get_json()
    assert staff["total"] == 1 and staff["items"][0]["claims"][0]["student_email"] == "s2@beta.edu.in"
    assert adm_b[0].get("/api/v1/admin/items?status=pending").get_json()["total"] == 0
    with app.app_context():
        assert Claim.query.count() == 1
