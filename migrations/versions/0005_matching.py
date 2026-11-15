"""Phase 5: trigram text search and suggested lost/found matches.

Additive only. Needs the pg_trgm extension (available on Neon and standard PostgreSQL).

Revision ID: 0005_matching
Revises: 0004_pickup_and_storage
Create Date: 2026-11-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_matching"
down_revision = "0004_pickup_and_storage"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_table(
        "item_match",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("college_id", sa.Integer(), sa.ForeignKey("college.id", ondelete="CASCADE"), nullable=False),
        sa.Column("found_item_id", sa.Integer(), sa.ForeignKey("item.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lost_item_id", sa.Integer(), sa.ForeignKey("item.id", ondelete="CASCADE"), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("reasons", postgresql.JSONB()),
        sa.Column("status", sa.String(20), nullable=False, server_default="suggested"),
        sa.Column("notified_at", sa.DateTime()),
        sa.Column("ai_verdict", sa.String(20)),
        sa.Column("ai_reason", sa.Text()),
        sa.Column("ai_checked_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("found_item_id", "lost_item_id", name="uq_item_match_pair"),
    )
    op.create_index("ix_item_match_college_id", "item_match", ["college_id"])
    op.create_index("ix_item_match_found_item_id", "item_match", ["found_item_id"])
    op.create_index("ix_item_match_lost_item_id", "item_match", ["lost_item_id"])
    # Fast typo-tolerant search on item names
    op.execute("CREATE INDEX IF NOT EXISTS ix_item_name_trgm ON item USING gin (lower(name) gin_trgm_ops)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_item_name_trgm")
    op.drop_table("item_match")
