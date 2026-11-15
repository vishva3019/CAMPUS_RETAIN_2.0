"""Phase 7: browser push subscriptions. Additive only.

Revision ID: 0008_push
Revises: 0007_rls
Create Date: 2026-11-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_push"
down_revision = "0007_rls"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "push_subscription",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False, unique=True),
        sa.Column("p256dh", sa.String(200), nullable=False),
        sa.Column("auth", sa.String(100), nullable=False),
        sa.Column("user_agent", sa.String(200)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_success_at", sa.DateTime()),
    )
    op.create_index("ix_push_subscription_user_id", "push_subscription", ["user_id"])


def downgrade():
    op.drop_table("push_subscription")
