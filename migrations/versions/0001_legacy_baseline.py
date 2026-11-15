"""Campus Retain 2.0 schema (user, item, claim).

On an existing 2.0 database these tables already exist, so this revision only
creates whatever is missing. It never alters or drops existing tables.

Revision ID: 0001_legacy_baseline
Revises:
Create Date: 2026-11-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_legacy_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    existing = set(sa.inspect(op.get_bind()).get_table_names())

    if "user" not in existing:
        op.create_table(
            "user",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("email", sa.String(120), nullable=False, unique=True),
            sa.Column("password", sa.String(255), nullable=False),
        )
    if "item" not in existing:
        op.create_table(
            "item",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("category", sa.String(50)),
            sa.Column("location", sa.String(150)),
            sa.Column("secret_detail", sa.Text()),
            sa.Column("image_data", sa.Text()),
            sa.Column("status", sa.String(30)),
            sa.Column("date_found", sa.DateTime()),
        )
    if "claim" not in existing:
        op.create_table(
            "claim",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("item_id", sa.Integer(), sa.ForeignKey("item.id"), nullable=False),
            sa.Column("student_id", sa.String(50)),
            sa.Column("student_email", sa.String(120)),
            sa.Column("phone", sa.String(20)),
            sa.Column("proof_description", sa.Text()),
            sa.Column("timestamp", sa.DateTime()),
        )


def downgrade():
    # Never drop 2.0 data automatically.
    pass
