"""Phase 2: pickup codes and handover records on claims.

Additive only. ``item_image`` and ``collection_point`` already exist (0002).

Revision ID: 0004_pickup_and_storage
Revises: 0003_enforce_tenant
Create Date: 2026-11-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_pickup_and_storage"
down_revision = "0003_enforce_tenant"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("claim", sa.Column("pickup_code_hash", sa.String(255)))
    op.add_column("claim", sa.Column("pickup_code_sent_at", sa.DateTime()))
    op.add_column("claim", sa.Column("pickup_code_expires_at", sa.DateTime()))
    op.add_column("claim", sa.Column("pickup_code_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("claim", sa.Column("collected_at", sa.DateTime()))
    op.add_column("claim", sa.Column("collected_by_id", sa.Integer(),
                                     sa.ForeignKey("user.id", ondelete="SET NULL")))


def downgrade():
    for col in ("collected_by_id", "collected_at", "pickup_code_attempts", "pickup_code_expires_at",
                "pickup_code_sent_at", "pickup_code_hash"):
        op.drop_column("claim", col)
