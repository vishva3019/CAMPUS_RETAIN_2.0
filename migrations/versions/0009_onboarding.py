"""Animated onboarding: student details on accounts, pending registrations, and which
colleges appear on the sign-up screen. Additive only.

Revision ID: 0009_onboarding
Revises: 0008_push
Create Date: 2026-11-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_onboarding"
down_revision = "0008_push"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("college", sa.Column("listed_on_signup", sa.Boolean(), nullable=False,
                                       server_default=sa.text("false")))
    op.add_column("user", sa.Column("student_id", sa.String(30)))
    op.add_column("user", sa.Column("department_name", sa.String(120)))
    op.add_column("user", sa.Column("year_of_study", sa.String(10)))
    op.create_index("uq_user_college_student_id", "user", ["college_id", "student_id"], unique=True,
                    postgresql_where=sa.text("student_id IS NOT NULL"))
    op.create_table(
        "pending_registration",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("college_id", sa.Integer(), sa.ForeignKey("college.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(120), nullable=False, unique=True),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("student_id", sa.String(30), nullable=False),
        sa.Column("department_id", sa.Integer(), sa.ForeignKey("department.id", ondelete="SET NULL")),
        sa.Column("department_name", sa.String(120), nullable=False),
        sa.Column("year_of_study", sa.String(10), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_pending_registration_college_id", "pending_registration", ["college_id"])


def downgrade():
    op.drop_table("pending_registration")
    op.drop_index("uq_user_college_student_id", table_name="user")
    op.drop_column("user", "year_of_study")
    op.drop_column("user", "department_name")
    op.drop_column("user", "student_id")
    op.drop_column("college", "listed_on_signup")
