"""Multi-tenant schema: colleges, roles, audit, notifications; tenant columns on 2.0 tables.

Additive only: new tables and new nullable columns. Existing rows are untouched;
run ``flask legacy adopt --slug <college>`` afterwards to assign them to a college,
then migration 0003 enforces college_id NOT NULL.

Revision ID: 0002_multi_tenant
Revises: 0001_legacy_baseline
Create Date: 2026-11-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_multi_tenant"
down_revision = "0001_legacy_baseline"
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB(astext_type=sa.Text())

# Snapshot of the built-in roles at the time of this migration.
# Later changes are applied with `flask rbac sync`.
PERMISSIONS = {
    "items.view": "Browse items in own college",
    "items.report": "Report found or lost items",
    "claims.submit": "Submit ownership claims",
    "items.manage": "Edit and remove item listings",
    "claims.review": "Approve or reject claims",
    "collection.verify": "Verify pickup codes and confirm handovers",
    "users.manage": "Manage students and staff in own college",
    "college.settings": "Configure college branding, campuses and collection points",
    "analytics.view": "View college analytics and exports",
    "audit.view": "View audit logs",
    "platform.manage": "Manage colleges, subscriptions and platform settings",
}
ROLES = [
    ("platform_super_admin", "Platform Super Admin", True, ["platform.manage", "audit.view"]),
    ("college_admin", "College Admin", False, [
        "items.view", "items.report", "items.manage", "claims.review", "collection.verify",
        "users.manage", "college.settings", "analytics.view", "audit.view"]),
    ("campus_moderator", "Campus Moderator", False, ["items.view", "items.report", "items.manage", "claims.review"]),
    ("security_staff", "Security Staff", False, ["items.view", "collection.verify"]),
    ("student", "Student", False, ["items.view", "items.report", "claims.submit"]),
]


def _ix(table, col, unique=False):
    op.create_index(f"ix_{table}_{col}", table, [col], unique=unique)


def upgrade():
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    now = sa.text("CURRENT_TIMESTAMP")

    # ---- tenancy
    op.create_table(
        "college",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(60), nullable=False, unique=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("short_name", sa.String(40)),
        sa.Column("city", sa.String(80)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("primary_color", sa.String(9)),
        sa.Column("logo_url", sa.String(500)),
        sa.Column("contact_email", sa.String(160)),
        sa.Column("support_office", sa.String(160)),
        sa.Column("pickup_instructions", sa.Text()),
        sa.Column("mail_from_name", sa.String(120)),
        sa.Column("inter_college_matching", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=now),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=now),
    )
    op.create_table(
        "college_domain",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("college_id", sa.Integer(), sa.ForeignKey("college.id", ondelete="CASCADE"), nullable=False),
        sa.Column("domain", sa.String(160), nullable=False, unique=True),
    )
    _ix("college_domain", "college_id")
    op.create_table(
        "campus",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("college_id", sa.Integer(), sa.ForeignKey("college.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("address", sa.String(300)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=now),
        sa.UniqueConstraint("college_id", "name"),
    )
    _ix("campus", "college_id")
    op.create_table(
        "department",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("college_id", sa.Integer(), sa.ForeignKey("college.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campus_id", sa.Integer(), sa.ForeignKey("campus.id", ondelete="SET NULL")),
        sa.Column("name", sa.String(120), nullable=False),
        sa.UniqueConstraint("college_id", "name"),
    )
    _ix("department", "college_id")
    _ix("department", "campus_id")

    # ---- access control
    perm_t = op.create_table(
        "permission",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(60), nullable=False, unique=True),
        sa.Column("description", sa.String(200)),
    )
    role_t = op.create_table(
        "role",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(40), nullable=False, unique=True),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("is_platform", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    rp_t = op.create_table(
        "role_permission",
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("role.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("permission_id", sa.Integer(), sa.ForeignKey("permission.id", ondelete="CASCADE"), primary_key=True),
    )
    codes = list(PERMISSIONS)
    op.bulk_insert(perm_t, [{"id": i + 1, "code": c, "description": PERMISSIONS[c]} for i, c in enumerate(codes)])
    op.bulk_insert(role_t, [{"id": i + 1, "name": n, "label": l, "is_platform": p}
                            for i, (n, l, p, _) in enumerate(ROLES)])
    op.bulk_insert(rp_t, [{"role_id": i + 1, "permission_id": codes.index(c) + 1}
                          for i, (_, _, _, perms) in enumerate(ROLES) for c in perms])
    # bulk_insert used explicit ids; move the sequences past them.
    if op.get_bind().dialect.name == "postgresql":
        op.execute("SELECT setval(pg_get_serial_sequence('permission', 'id'), (SELECT MAX(id) FROM permission))")
        op.execute("SELECT setval(pg_get_serial_sequence('role', 'id'), (SELECT MAX(id) FROM role))")

    # ---- operations tables
    op.create_table(
        "collection_point",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("college_id", sa.Integer(), sa.ForeignKey("college.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campus_id", sa.Integer(), sa.ForeignKey("campus.id", ondelete="SET NULL")),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("opening_hours", sa.String(160)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=now),
    )
    _ix("collection_point", "college_id")
    _ix("collection_point", "campus_id")
    op.create_table(
        "event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("college_id", sa.Integer(), sa.ForeignKey("college.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campus_id", sa.Integer(), sa.ForeignKey("campus.id", ondelete="SET NULL")),
        sa.Column("slug", sa.String(60), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=now),
        sa.UniqueConstraint("college_id", "slug"),
    )
    _ix("event", "college_id")

    # ---- tenant columns on 2.0 tables (all nullable / defaulted: no rewrite of existing rows)
    op.add_column("user", sa.Column("college_id", sa.Integer(), sa.ForeignKey("college.id")))
    op.add_column("user", sa.Column("campus_id", sa.Integer(), sa.ForeignKey("campus.id", ondelete="SET NULL")))
    op.add_column("user", sa.Column("department_id", sa.Integer(), sa.ForeignKey("department.id", ondelete="SET NULL")))
    op.add_column("user", sa.Column("role_id", sa.Integer(), sa.ForeignKey("role.id")))
    op.add_column("user", sa.Column("full_name", sa.String(120)))
    op.add_column("user", sa.Column("phone", sa.String(20)))
    op.add_column("user", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("user", sa.Column("email_verified_at", sa.DateTime()))
    op.add_column("user", sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("user", sa.Column("locked_until", sa.DateTime()))
    op.add_column("user", sa.Column("session_version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("user", sa.Column("last_login_at", sa.DateTime()))
    op.add_column("user", sa.Column("created_at", sa.DateTime()))
    for col in ("college_id", "campus_id", "role_id"):
        _ix("user", col)

    op.add_column("item", sa.Column("college_id", sa.Integer(), sa.ForeignKey("college.id")))
    op.add_column("item", sa.Column("campus_id", sa.Integer(), sa.ForeignKey("campus.id", ondelete="SET NULL")))
    op.add_column("item", sa.Column("event_id", sa.Integer(), sa.ForeignKey("event.id", ondelete="SET NULL")))
    op.add_column("item", sa.Column("collection_point_id", sa.Integer(), sa.ForeignKey("collection_point.id", ondelete="SET NULL")))
    op.add_column("item", sa.Column("reported_by_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="SET NULL")))
    op.add_column("item", sa.Column("kind", sa.String(10), nullable=False, server_default="found"))
    op.add_column("item", sa.Column("description", sa.Text()))
    op.add_column("item", sa.Column("occurred_on", sa.Date()))
    op.add_column("item", sa.Column("updated_at", sa.DateTime()))
    op.add_column("item", sa.Column("removed_at", sa.DateTime()))
    op.add_column("item", sa.Column("removed_by_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="SET NULL")))
    for col in ("college_id", "campus_id", "reported_by_id"):
        _ix("item", col)
    op.create_index("ix_item_college_status_date", "item", ["college_id", "status", "date_found"])

    op.add_column("claim", sa.Column("college_id", sa.Integer(), sa.ForeignKey("college.id")))
    op.add_column("claim", sa.Column("claimant_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="SET NULL")))
    op.add_column("claim", sa.Column("status", sa.String(20), nullable=False, server_default="pending"))
    op.add_column("claim", sa.Column("reviewed_by_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="SET NULL")))
    op.add_column("claim", sa.Column("reviewed_at", sa.DateTime()))
    op.add_column("claim", sa.Column("review_remarks", sa.Text()))
    for col in ("college_id", "claimant_id", "item_id"):
        _ix("claim", col)

    # ---- tables that reference user
    op.create_table(
        "item_image",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("item.id", ondelete="CASCADE"), nullable=False),
        sa.Column("college_id", sa.Integer(), sa.ForeignKey("college.id"), nullable=False),
        sa.Column("storage_key", sa.String(400), nullable=False, unique=True),
        sa.Column("content_type", sa.String(40), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer()),
        sa.Column("height", sa.Integer()),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=now),
    )
    _ix("item_image", "item_id")
    _ix("item_image", "college_id")
    op.create_table(
        "notification",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("college_id", sa.Integer(), sa.ForeignKey("college.id", ondelete="CASCADE")),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text()),
        sa.Column("link", sa.String(300)),
        sa.Column("read_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=now),
    )
    _ix("notification", "college_id")
    op.create_index("ix_notification_user_unread", "notification", ["user_id", "read_at"])
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("college_id", sa.Integer(), sa.ForeignKey("college.id", ondelete="SET NULL")),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="SET NULL")),
        sa.Column("actor_email", sa.String(160)),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("target_type", sa.String(40)),
        sa.Column("target_id", sa.Integer()),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("details", JSONB),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=now),
    )
    _ix("audit_log", "actor_id")
    _ix("audit_log", "action")
    op.create_index("ix_audit_log_college_created", "audit_log", ["college_id", "created_at"])
    op.create_table(
        "subscription",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("college_id", sa.Integer(), sa.ForeignKey("college.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plan", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("current_period_start", sa.DateTime()),
        sa.Column("current_period_end", sa.DateTime()),
        sa.Column("external_ref", sa.String(120)),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=now),
    )
    _ix("subscription", "college_id")
    op.create_table(
        "platform_setting",
        sa.Column("key", sa.String(80), primary_key=True),
        sa.Column("value", JSONB),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=now),
    )

    # email_code may already exist (2.0 security patch); create it only if missing.
    if "email_code" not in existing:
        op.create_table(
            "email_code",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("email", sa.String(120), nullable=False),
            sa.Column("purpose", sa.String(20), nullable=False),
            sa.Column("code_hash", sa.String(255), nullable=False),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=now),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
        )
        _ix("email_code", "email")


def downgrade():
    for table in ("platform_setting", "subscription", "audit_log", "notification", "item_image"):
        op.drop_table(table)
    for col in ("review_remarks", "reviewed_at", "reviewed_by_id", "status", "claimant_id", "college_id"):
        op.drop_column("claim", col)
    op.drop_index("ix_claim_item_id", "claim")
    op.drop_index("ix_item_college_status_date", "item")
    for col in ("removed_by_id", "removed_at", "updated_at", "occurred_on", "description", "kind",
                "reported_by_id", "collection_point_id", "event_id", "campus_id", "college_id"):
        op.drop_column("item", col)
    for col in ("created_at", "last_login_at", "session_version", "locked_until", "failed_login_count",
                "email_verified_at", "is_active", "phone", "full_name", "role_id", "department_id",
                "campus_id", "college_id"):
        op.drop_column("user", col)
    for table in ("event", "collection_point", "role_permission", "role", "permission",
                  "department", "campus", "college_domain", "college"):
        op.drop_table(table)
