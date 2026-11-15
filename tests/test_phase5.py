"""Phase 5: text matching, duplicate warnings, typo-tolerant search, claim warnings,
and the optional Claude features (tested against a fake client; no network)."""
import io
from types import SimpleNamespace

import pytest

from campus_retain.extensions import db
from campus_retain.models import Claim, ClaimStatus, ItemMatch, MatchStatus, Notification, User, utcnow
from campus_retain.services import ai as ai_service

from .conftest import api_token, login, make_college, make_item, make_user, png_bytes


@pytest.fixture
def world(new_client):
    college = make_college()
    other = make_college(slug="beta", domains=("beta.edu.in",))
    for email, c, role in [("owner@alpha.edu.in", college, "student"), ("finder@alpha.edu.in", college, "student"),
                           ("admin@alpha.edu.in", college, "college_admin"), ("x@beta.edu.in", other, "student"),
                           ("admin@beta.edu.in", other, "college_admin")]:
        make_user(email, c, role=role)
    clients = {}
    for email in ("owner@alpha.edu.in", "finder@alpha.edu.in", "admin@alpha.edu.in", "x@beta.edu.in", "admin@beta.edu.in"):
        cl = new_client()
        login(cl, email, path="/admin_login" if "admin" in email else "/login")
        clients[email.split("@")[0] + ("@beta" if "beta" in email else "")] = (cl, api_token(cl))
    return college, other, clients


def report(ct, **data):
    c, token = ct
    resp = c.post("/api/report", headers={"X-CSRFToken": token}, data={"location": "Library", **data},
                  content_type="multipart/form-data")
    db.session.expire_all()
    return resp


def test_found_report_matches_lost_report_and_alerts_owner(world, outbox):
    _, _, c = world
    lost_id = report(c["owner"], kind="lost", name="Black leather wallet", category="Accessories",
                     description="Has a library card inside").get_json()["id"]
    outbox.clear()
    found_id = report(c["finder"], name="black wallet leather", category="Accessories", location="Library steps").get_json()["id"]
    match = ItemMatch.query.one()
    assert (match.found_item_id, match.lost_item_id) == (found_id, lost_id) and match.score >= 0.45
    assert match.reasons["same_category"] is True
    note = Notification.query.filter_by(kind="lost.suggested_match").one()
    assert note.user_id == User.query.filter_by(email="owner@alpha.edu.in").one().id
    assert any(m["to"] == "owner@alpha.edu.in" and "may be yours" in m["body"] for m in outbox)
    mine = c["owner"][0].get("/api/v1/me/matches").get_json()["items"]
    assert [m["item"]["id"] for m in mine] == [found_id]
    # unrelated item doesn't match; other colleges never match
    report(c["finder"], name="Blue umbrella", category="Other")
    report(c["x@beta"], name="Black leather wallet", category="Accessories")
    assert ItemMatch.query.count() == 1


def test_owner_dismisses_and_approval_confirms_matches(world):
    _, _, c = world
    report(c["owner"], kind="lost", name="Silver steel bottle", category="Bottles")
    found_id = report(c["finder"], name="Steel bottle silver", category="Bottles").get_json()["id"]
    match = ItemMatch.query.one()
    assert c["finder"][0].post(f"/api/v1/matches/{match.id}/dismiss", headers={"X-CSRFToken": c["finder"][1]}).status_code == 404
    c["owner"][0].post("/api/claim", headers={"X-CSRFToken": c["owner"][1]},
                       json={"item_id": found_id, "student_id": "1", "proof_description": "dent near the cap, my initials"})
    c["admin"][0].post(f"/api/admin/approve/{found_id}", headers={"X-CSRFToken": c["admin"][1]}, json={})
    db.session.expire_all()
    assert db.session.get(ItemMatch, match.id).status == MatchStatus.CONFIRMED


def test_duplicate_warning_before_posting(world):
    _, _, c = world
    report(c["finder"], name="Red Casio calculator", category="Electronics")
    dup = c["owner"][0].get("/api/v1/items/similar?kind=found&name=red casio calculator&category=Electronics").get_json()
    assert [i["name"] for i in dup["items"]] == ["Red Casio calculator"]
    none = c["owner"][0].get("/api/v1/items/similar?kind=found&name=football&category=Sports").get_json()
    assert none["items"] == []
    assert c["x@beta"][0].get("/api/v1/items/similar?kind=found&name=red casio calculator").get_json()["items"] == []


def test_search_tolerates_typos_and_searches_descriptions(world):
    college, _, c = world
    make_item(college, name="Headphones", category="Electronics", description="Sony noise cancelling")
    make_item(college, name="Water bottle", category="Bottles")
    names = lambda q: [i["name"] for i in c["owner"][0].get(f"/api/v1/items?q={q}").get_json()["items"]]
    assert names("headphnes") == ["Headphones"]          # typo
    assert names("sony") == ["Headphones"]               # description
    assert names("bottle") == ["Water bottle"]
    assert names("zzzz") == []


def test_reviewers_see_claim_warnings(world):
    college, _, c = world
    item = make_item(college, name="Blue bag", description="Blue backpack with a keychain", location="Canteen")
    finder = User.query.filter_by(email="finder@alpha.edu.in").one()
    for _ in range(2):
        db.session.add(Claim(item_id=make_item(college).id, college_id=college.id, claimant_id=finder.id,
                             status=ClaimStatus.REJECTED, reviewed_at=utcnow()))
    db.session.commit()
    c["finder"][0].post("/api/claim", headers={"X-CSRFToken": c["finder"][1]},
                        json={"item_id": item.id, "student_id": "1", "proof_description": "Blue backpack with a keychain"})
    rows = c["admin"][0].get("/api/v1/admin/items?status=pending").get_json()["items"]
    codes = {f["code"] for f in rows[0]["claims"][0]["flags"]}
    assert {"recent_rejections", "copied_listing"} <= codes
    assert "flags" not in str(c["owner"][0].get("/api/v1/items").get_json())


# ---------------------------------------------------------------- Claude (fake client)

class FakeClient:
    def __init__(self, parsed, stop_reason="end_turn"):
        self.calls = []
        outer = self

        class _Messages:
            def parse(self, **kw):
                outer.calls.append(kw)
                return SimpleNamespace(stop_reason=stop_reason, parsed_output=parsed)

        self.beta = SimpleNamespace(messages=_Messages())


@pytest.fixture
def ai_on(app, monkeypatch):
    app.config["ANTHROPIC_API_KEY"] = "test-key-not-real"
    yield monkeypatch
    app.config["ANTHROPIC_API_KEY"] = None


def describe(ct, data=None):
    c, token = ct
    return c.post("/api/v1/ai/describe", headers={"X-CSRFToken": token}, content_type="multipart/form-data",
                  data={"image": (io.BytesIO(data or png_bytes()), "p.png", "image/png")})


def test_ai_is_off_without_a_key(world):
    _, _, c = world
    assert c["owner"][0].get("/api/v1/session").get_json()["config"]["ai_enabled"] is False
    assert describe(c["owner"]).status_code == 503


def test_photo_description_uses_structured_output_and_fallbacks(world, ai_on):
    _, _, c = world
    fake = FakeClient(ai_service.PhotoSuggestion(is_item_photo=True, name="Black umbrella", category="Bogus", description="Folding, wooden handle"))
    ai_on.setattr(ai_service, "_client", lambda: fake)
    resp = describe(c["owner"])
    assert resp.status_code == 200
    assert resp.get_json() == {"name": "Black umbrella", "category": "Other", "description": "Folding, wooden handle"}
    call = fake.calls[0]
    assert call["model"] == "claude-opus-5-5" and call["fallbacks"] == "default"
    assert call["betas"] == ["server-side-fallback-2026-07-01"] and call["output_format"] is ai_service.PhotoSuggestion
    image_block = call["messages"][0]["content"][0]
    assert image_block["type"] == "image" and image_block["source"]["media_type"] == "image/jpeg"
    assert describe(c["owner"], b"not an image").status_code == 400


def test_photo_description_handles_refusal_and_non_item(world, ai_on):
    _, _, c = world
    ai_on.setattr(ai_service, "_client", lambda: FakeClient(None, stop_reason="refusal"))
    assert describe(c["owner"]).status_code == 422
    ai_on.setattr(ai_service, "_client", lambda: FakeClient(ai_service.PhotoSuggestion(is_item_photo=False, name="", category="Other", description="")))
    resp = describe(c["owner"])
    assert resp.status_code == 422 and "doesn't look like" in resp.get_json()["error"]


def test_ai_match_check_is_staff_only_and_uses_public_text(world, ai_on):
    college, _, c = world
    report(c["owner"], kind="lost", name="Grey hoodie", category="Clothing")
    report(c["finder"], name="Grey hoodie", category="Clothing", secret_detail="NAME-TAG-SECRET")
    match = ItemMatch.query.one()
    fake = FakeClient(ai_service.MatchVerdict(verdict="Likely", reason="Same colour and type, found a day later."))
    ai_on.setattr(ai_service, "_client", lambda: fake)
    url = f"/api/v1/matches/{match.id}/ai-check"
    assert c["owner"][0].post(url, headers={"X-CSRFToken": c["owner"][1]}).status_code == 403
    assert c["admin@beta"][0].post(url, headers={"X-CSRFToken": c["admin@beta"][1]}).status_code == 404
    resp = c["admin"][0].post(url, headers={"X-CSRFToken": c["admin"][1]})
    assert resp.status_code == 200 and resp.get_json()["match"]["ai_verdict"] == "likely"
    assert "NAME-TAG-SECRET" not in str(fake.calls[0]["messages"])
    listed = c["admin"][0].get(f"/api/v1/admin/items/{match.found_item_id}/matches").get_json()["items"]
    assert listed[0]["ai_reason"].startswith("Same colour")
