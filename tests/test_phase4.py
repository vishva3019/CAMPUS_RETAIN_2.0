"""Phase 4: analytics from real rows, Excel/PDF exports, activity log, platform stats."""
import io
from datetime import timedelta

import pytest
from openpyxl import load_workbook

from campus_retain.extensions import db
from campus_retain.models import AuditLog, Claim, ClaimStatus, ItemKind, ItemStatus, utcnow

from .conftest import api_token, login, make_campus, make_college, make_item, make_user


@pytest.fixture
def world(new_client):
    college = make_college()
    other = make_college(slug="beta", domains=("beta.edu.in",))
    make_user("s1@alpha.edu.in", college)
    make_user("admin@alpha.edu.in", college, role="college_admin")
    make_user("guard@alpha.edu.in", college, role="security_staff")
    make_user("root@platform.test", None, role="platform_super_admin")
    clients = {}
    for email, path in [("s1@alpha.edu.in", "/login"), ("admin@alpha.edu.in", "/admin_login"),
                        ("guard@alpha.edu.in", "/admin_login"), ("root@platform.test", "/admin_login")]:
        c = new_client()
        login(c, email, path=path)
        clients[email.split("@")[0]] = (c, api_token(c))
    return college, other, clients


def seed(college, other):
    now = utcnow()
    north = make_campus(college, "North")
    a = make_item(college, name="Phone", category="Electronics", campus=north)
    a.date_found = now - timedelta(days=10)
    b = make_item(college, name="Keys", category="Keys", status=ItemStatus.RETURNED)
    b.date_found = now - timedelta(days=6)
    c = make_item(college, name="Bottle", category="Bottles", status=ItemStatus.CLAIMED)
    make_item(college, name="Gone", status=ItemStatus.REMOVED)
    make_item(college, name="Lost hoodie", kind=ItemKind.LOST)
    make_item(other, name="Other college item")
    db.session.add_all([
        Claim(item_id=b.id, college_id=college.id, status=ClaimStatus.COLLECTED, timestamp=now - timedelta(days=5),
              reviewed_at=now - timedelta(days=4), collected_at=now - timedelta(days=2)),
        Claim(item_id=c.id, college_id=college.id, status=ClaimStatus.APPROVED, timestamp=now - timedelta(days=3),
              reviewed_at=now - timedelta(days=1)),
        Claim(item_id=a.id, college_id=college.id, status=ClaimStatus.REJECTED, timestamp=now - timedelta(days=8)),
    ])
    db.session.commit()


def test_analytics_numbers_come_from_real_rows(world):
    college, other, c = world
    seed(college, other)
    data = c["admin"][0].get("/api/v1/admin/analytics").get_json()
    t = data["totals"]
    assert t["found_reported"] == 3 and t["lost_reported"] == 1      # removed + other college excluded
    assert t["recovered"] == 2 and t["recovery_rate"] == round(2 / 3, 4)
    assert t["returned"] == 1 and t["avg_days_to_return"] == 4.0
    assert data["claim_outcomes"]["rejected"] == 1 and data["claim_outcomes"]["approved"] == 1
    assert data["backlog"]["awaiting_pickup"] == 1
    cats = {x["category"]: x for x in data["by_category"]}
    assert cats["Keys"]["recovered"] == 1 and cats["Electronics"]["found"] == 1
    assert sum(m["found"] for m in data["monthly"]) == 3
    assert {x["campus"] for x in data["by_campus"]} == {"North", "Not set"}


def test_empty_college_has_no_made_up_rates(world):
    _, _, c = world
    t = c["admin"][0].get("/api/v1/admin/analytics").get_json()["totals"]
    assert t["found_reported"] == 0 and t["recovery_rate"] is None and t["avg_days_to_return"] is None


def test_analytics_period_validation_and_permissions(world):
    _, _, c = world
    assert c["admin"][0].get("/api/v1/admin/analytics?from=2026-12-01&to=2026-01-01").status_code == 400
    assert c["admin"][0].get("/api/v1/admin/analytics?from=nope").status_code == 400
    assert c["s1"][0].get("/api/v1/admin/analytics").status_code == 403
    assert c["guard"][0].get("/api/v1/admin/analytics").status_code == 403
    assert c["root"][0].get("/api/v1/admin/analytics").status_code == 403


def test_excel_and_pdf_exports(world):
    college, other, c = world
    seed(college, other)
    resp = c["admin"][0].get("/api/v1/admin/analytics.xlsx")
    assert resp.status_code == 200 and "attachment" in resp.headers["Content-Disposition"]
    wb = load_workbook(io.BytesIO(resp.data))
    assert wb.sheetnames == ["Summary", "Monthly", "By category", "By campus", "Claim outcomes", "Items"]
    names = [r[2] for r in wb["Items"].iter_rows(min_row=2, values_only=True)]
    assert "Phone" in names and "Other college item" not in names
    flat = str([list(r) for r in wb["Items"].iter_rows(values_only=True)])
    assert "TOPSECRET-STICKER" not in flat                            # private detail never exported
    pdf = c["admin"][0].get("/api/v1/admin/analytics.pdf")
    assert pdf.status_code == 200 and pdf.data[:5] == b"%PDF-" and pdf.mimetype == "application/pdf"
    assert AuditLog.query.filter_by(action="analytics.exported").count() == 2
    assert c["s1"][0].get("/api/v1/admin/analytics.xlsx").status_code == 403


def test_activity_log_is_college_scoped(world):
    college, other, c = world
    from campus_retain.services.audit import audit
    audit("item.reported", None, college_id=college.id, email="x@alpha.edu.in")
    audit("item.reported", None, college_id=other.id, email="y@beta.edu.in")
    db.session.commit()
    data = c["admin"][0].get("/api/v1/admin/audit?action=item.").get_json()
    assert [e["actor"] for e in data["items"]] == ["x@alpha.edu.in"] and "item.reported" in data["actions"]
    assert c["s1"][0].get("/api/v1/admin/audit").status_code == 403
    assert c["guard"][0].get("/api/v1/admin/audit").status_code == 403
    all_entries = c["root"][0].get("/api/v1/platform/audit?action=item.").get_json()["items"]
    assert {e["actor"] for e in all_entries} == {"x@alpha.edu.in", "y@beta.edu.in"}
    assert c["admin"][0].get("/api/v1/platform/audit").status_code == 403


def test_platform_stats(world):
    college, other, c = world
    seed(college, other)
    data = c["root"][0].get("/api/v1/platform/stats").get_json()
    rows = {r["name"]: r for r in data["colleges"]}
    assert rows[college.name]["found"] == 3 and rows[college.name]["recovered"] == 2
    assert rows[other.name]["found"] == 1 and data["totals"]["found"] == 4
    assert c["admin"][0].get("/api/v1/platform/stats").status_code == 403
