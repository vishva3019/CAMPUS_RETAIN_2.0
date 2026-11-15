"""Pickup reminders: remember when a student was reminded about an uncollected item.

Revision ID: 0010_pickup_reminders
Revises: 0009_onboarding
Create Date: 2026-11-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_pickup_reminders"
down_revision = "0009_onboarding"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("claim", sa.Column("pickup_reminded_at", sa.DateTime()))


def downgrade():
    op.drop_column("claim", "pickup_reminded_at")
