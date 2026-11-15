"""Phase 6: approximate item location, QR item tags. Additive only.

(The event table and college.inter_college_matching already exist from 0002.)

Revision ID: 0006_network_events_tags
Revises: 0005_matching
Create Date: 2026-11-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_network_events_tags"
down_revision = "0005_matching"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("item", sa.Column("latitude", sa.Numeric(8, 5)))
    op.add_column("item", sa.Column("longitude", sa.Numeric(8, 5)))
    op.create_table(
        "item_tag",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("college_id", sa.Integer(), sa.ForeignKey("college.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(24), nullable=False, unique=True),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("scan_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_scanned_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_item_tag_college_id", "item_tag", ["college_id"])
    op.create_index("ix_item_tag_owner_id", "item_tag", ["owner_id"])
    op.create_index("ix_item_event_id", "item", ["event_id"])


def downgrade():
    op.drop_index("ix_item_event_id", "item")
    op.drop_table("item_tag")
    op.drop_column("item", "longitude")
    op.drop_column("item", "latitude")
