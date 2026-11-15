"""Test fixtures. Tests run against PostgreSQL (TEST_DATABASE_URL) so partial
indexes, row locks and JSONB behave exactly as in production.

    createdb campus_retain_test
    TEST_DATABASE_URL=postgresql:///campus_retain_test pytest
"""
import io
import os
import re

import pytest
from flask.testing import FlaskClient
from PIL import Image
from werkzeug.security import generate_password_hash

os.environ.setdefault("TEST_DATABASE_URL", "postgresql:///campus_retain_test")

from campus_retain import create_app  # noqa: E402
from campus_retain.extensions import db  # noqa: E402
from campus_retain.models import (Campus, College, CollegeDomain, CollegeStatus,  # noqa: E402
                                  Item, ItemStatus, User, utcnow)
from campus_retain.security import get_role, sync_roles  # noqa: E402

PASSWORD = "correct-horse-battery"


class FreshContextClient(FlaskClient):
    """Run every request in its own app context, as in production. Without this the
    test's outer app context (and its ``g``) would be shared by all requests."""

    def open(self, *args, **kwargs):
        with self.application.app_context():
            return super().open(*args, **kwargs)


@pytest.fixture(scope="session")
def app():
    app = create_app("test")
    app.test_client_class = FreshContextClient
    with app.app_context():
        db.session.execute(db.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        db.session.commit()
        db.drop_all()
        db.create_all()
        from campus_retain.rls import install_rls
        install_rls(db.session.connection())   # bound only for non-superuser roles (see test_rls.py)
        db.session.commit()
        sync_roles()
    yield app
    with app.app_context():
        db.drop_all()


@pytest.fixture(autouse=True)
def clean_db(app):
    with app.app_context():
        yield
        db.session.rollback()
        tables = [t.name for t in reversed(db.metadata.sorted_tables) if t.name not in ("role", "permission", "role_permission")]
        db.session.execute(db.text("TRUNCATE " + ", ".join(f'"{t}"' for t in tables) + " RESTART IDENTITY CASCADE"))
        db.session.commit()
        app.extensions["mail_outbox"] = []


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def new_client(app):
    return lambda: app.test_client()


@pytest.fixture
def outbox(app):
    app.extensions["mail_outbox"] = []
    return app.extensions["mail_outbox"]


# ---------------------------------------------------------------- factories

def make_college(slug="alpha", domains=("alpha.edu.in",), status=CollegeStatus.ACTIVE, **kw):
    college = College(slug=slug, name=kw.pop("name", f"{slug.title()} College"), status=status,
                      support_office=kw.pop("support_office", f"{slug.title()} Student Services"), **kw)
    college.domains = [CollegeDomain(domain=d) for d in domains]
    db.session.add(college)
    db.session.commit()
    return college


def make_user(email, college=None, role="student", verified=True, password=PASSWORD, campus=None):
    user = User(email=email, password=generate_password_hash(password), role_id=get_role(role).id,
                college_id=college.id if college else None, campus_id=campus.id if campus else None,
                email_verified_at=utcnow() if verified else None, created_at=utcnow())
    db.session.add(user)
    db.session.commit()
    return user


def make_item(college, name="Black wallet", status=ItemStatus.AVAILABLE, campus=None, reporter=None, **kw):
    item = Item(college_id=college.id, name=name, category=kw.pop("category", "Accessories"),
                location=kw.pop("location", "Library"), secret_detail=kw.pop("secret_detail", "TOPSECRET-STICKER"),
                status=status, campus_id=campus.id if campus else None,
                reported_by_id=reporter.id if reporter else None, date_found=utcnow(), **kw)
    db.session.add(item)
    db.session.commit()
    return item


def make_campus(college, name="Main"):
    campus = Campus(college_id=college.id, name=name)
    db.session.add(campus)
    db.session.commit()
    return campus


# ---------------------------------------------------------------- request helpers

def csrf_from(html):
    m = re.search(r'name="csrf_token" value="([^"]+)"', html) or re.search(r'name="csrf-token" content="([^"]+)"', html)
    assert m, "no CSRF token on page"
    return m.group(1)


def get_csrf(client, path="/login"):
    return csrf_from(client.get(path).get_data(as_text=True))


def login(client, email, password=PASSWORD, path="/login"):
    token = get_csrf(client, path)
    return client.post(path, data={"email": email, "password": password, "csrf_token": token})


def api_token(client):
    """CSRF token for JSON calls (same session token the pages embed)."""
    resp = client.get("/login")
    if resp.status_code == 302:  # logged in: any page with the meta tag works
        resp = client.get(resp.location)
    return csrf_from(resp.get_data(as_text=True))


def last_code(outbox, to=None):
    for mail in reversed(outbox):
        if to is None or mail["to"] == to:
            m = re.search(r"\b(\d{6})\b", mail["body"])
            if m:
                return m.group(1)
    raise AssertionError("no code email found")


def png_bytes(size=(64, 48), color=(200, 30, 30)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()
