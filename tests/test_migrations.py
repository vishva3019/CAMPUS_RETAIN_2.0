"""Alembic migrations against a real PostgreSQL database shaped like Campus Retain 2.0.

Uses a separate database (MIGRATION_TEST_DATABASE_URL, default campus_retain_migtest)
which is wiped at the start of each test.
"""
import os

import pytest
from flask_migrate import upgrade
from sqlalchemy import create_engine, inspect, text
from werkzeug.security import generate_password_hash

from campus_retain import create_app
from campus_retain.config import normalize_database_url
from campus_retain.extensions import db

MIG_URL = normalize_database_url(os.environ.get("MIGRATION_TEST_DATABASE_URL", "postgresql:///campus_retain_migtest"))

LEGACY_SCHEMA = """
CREATE TABLE "user" (id SERIAL PRIMARY KEY, email VARCHAR(120) NOT NULL UNIQUE, password VARCHAR(255) NOT NULL);
CREATE TABLE item (id SERIAL PRIMARY KEY, name VARCHAR(120) NOT NULL, category VARCHAR(50), location VARCHAR(150),
                   secret_detail TEXT, image_data TEXT, status VARCHAR(30), date_found TIMESTAMP WITHOUT TIME ZONE);
CREATE TABLE claim (id SERIAL PRIMARY KEY, item_id INTEGER NOT NULL REFERENCES item(id), student_id VARCHAR(50),
                    student_email VARCHAR(120), phone VARCHAR(20), proof_description TEXT,
                    timestamp TIMESTAMP WITHOUT TIME ZONE);
"""


def reset_database(with_legacy_data):
    engine = create_engine(MIG_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
        if with_legacy_data:
            conn.execute(text(LEGACY_SCHEMA))
            pw = generate_password_hash("legacy-password")
            conn.execute(text('INSERT INTO "user" (email, password) VALUES (:a, :p), (:b, :p)'),
                         {"a": "old1@ced.example.edu.in", "b": "old2@ced.example.edu.in", "p": pw})
            conn.execute(text("""
                INSERT INTO item (name, status, date_found, secret_detail) VALUES
                ('Umbrella', 'Available', '2026-08-01', 's1'),
                ('Laptop',   'Pending',   '2026-08-02', 's2'),
                ('ID card',  'Claimed',   '2026-08-03', 's3'),
                ('Bottle',   'Pending',   '2026-08-04', 's4');
                INSERT INTO claim (item_id, student_email, proof_description, timestamp) VALUES
                (1, 'old1@ced.example.edu.in', 'rejected long ago', '2026-08-05'),
                (2, 'old1@ced.example.edu.in', 'first try',         '2026-08-06'),
                (2, 'old2@ced.example.edu.in', 'latest try',        '2026-08-07'),
                (3, 'unknown@elsewhere.com',   'approved one',      '2026-08-08');
            """))
    engine.dispose()


@pytest.fixture
def mig_app():
    app = create_app("test", {"SQLALCHEMY_DATABASE_URI": MIG_URL})
    with app.app_context():
        yield app
        db.session.remove()
        db.engine.dispose()


def cli(app, *args):
    result = app.test_cli_runner().invoke(args=list(args))
    assert result.exit_code == 0, result.output + repr(result.exception)
    return result.output


def test_upgrade_existing_2_0_database_in_place(mig_app):
    reset_database(with_legacy_data=True)
    upgrade(revision="0002_multi_tenant")

    cli(mig_app, "college", "create", "--name", "Example University", "--slug", "example",
        "--domain", "ced.example.edu.in", "--support-office", "Student Services", "--active")
    out = cli(mig_app, "legacy", "adopt", "--slug", "example", "--yes")
    assert "2 users, 4 items, 4 claims" in out

    db.session.remove()
    upgrade()  # 0003: enforce NOT NULL + one-active-claim index

    conn = db.session.connection()
    insp = inspect(conn)
    cols = {c["name"]: c for c in insp.get_columns("item")}
    assert cols["college_id"]["nullable"] is False
    assert {c["name"]: c for c in insp.get_columns("claim")}["college_id"]["nullable"] is False
    assert "uq_claim_one_active_per_item" in {i["name"] for i in insp.get_indexes("claim")}

    rows = conn.execute(text("SELECT c.id, c.status, c.claimant_id IS NOT NULL FROM claim c ORDER BY c.id")).fetchall()
    assert [(r[1], r[2]) for r in rows] == [
        ("closed", True),     # item 1 is Available: the old claim's outcome was never recorded
        ("closed", True),     # older claim on item 2
        ("pending", True),    # latest claim on the Pending item stays reviewable
        ("approved", False),  # Claimed item; claimant email has no account
    ]
    statuses = dict(conn.execute(text("SELECT name, status FROM item")).fetchall())
    assert statuses == {"Umbrella": "Available", "Laptop": "Pending", "ID card": "Claimed", "Bottle": "Available"}
    users = conn.execute(text('SELECT u.email_verified_at, r.name FROM "user" u JOIN role r ON r.id = u.role_id')).fetchall()
    assert all(v is None and r == "student" for v, r in users)
    assert conn.execute(text("SELECT COUNT(*) FROM role")).scalar() == 5

    # The migrated app works: legacy user signs in and is asked to confirm their email once.
    c = mig_app.test_client()
    from .conftest import get_csrf
    token = get_csrf(c)
    resp = c.post("/login", data={"email": "old1@ced.example.edu.in", "password": "legacy-password", "csrf_token": token})
    assert resp.status_code == 200 and "Confirm" in resp.get_data(as_text=True)

    # Adoption is idempotent
    assert "0 users, 0 items, 0 claims" in cli(mig_app, "legacy", "adopt", "--slug", "example", "--yes")


def test_enforce_step_refuses_unadopted_rows(mig_app):
    reset_database(with_legacy_data=True)
    upgrade(revision="0002_multi_tenant")
    with pytest.raises(SystemExit):   # Flask-Migrate exits after logging the RuntimeError
        upgrade()
    db.session.rollback()


def test_fresh_database_matches_models(mig_app):
    reset_database(with_legacy_data=False)
    upgrade()
    insp = inspect(db.engine)
    assert set(insp.get_table_names()) - {"alembic_version"} == set(db.metadata.tables)
    for table in db.metadata.sorted_tables:
        db_cols = {c["name"] for c in insp.get_columns(table.name)}
        assert db_cols == set(table.columns.keys()), table.name
        db_indexes = {i["name"] for i in insp.get_indexes(table.name)}
        model_indexes = {i.name for i in table.indexes}
        assert model_indexes <= db_indexes, (table.name, model_indexes - db_indexes)
