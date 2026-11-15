"""Enforce tenancy: item/claim college_id NOT NULL; one active claim per item.

Refuses to run while 2.0 rows have no college. Run ``flask legacy adopt`` first.

Revision ID: 0003_enforce_tenant
Revises: 0002_multi_tenant
Create Date: 2026-11-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_enforce_tenant"
down_revision = "0002_multi_tenant"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    for table in ("item", "claim"):
        orphans = bind.execute(sa.text(f'SELECT COUNT(*) FROM "{table}" WHERE college_id IS NULL')).scalar()
        if orphans:
            raise RuntimeError(
                f"{orphans} {table} rows have no college. Run "
                "'flask db upgrade 0002_multi_tenant', create the college, run "
                "'flask legacy adopt --slug <college>', then 'flask db upgrade' again."
            )

    active = bind.execute(sa.text(
        "SELECT item_id FROM claim WHERE status IN ('pending', 'approved') "
        "GROUP BY item_id HAVING COUNT(*) > 1")).fetchall()
    if active:
        raise RuntimeError("Items with more than one active claim: "
                           + ", ".join(str(r[0]) for r in active) + ". Resolve them first.")

    op.alter_column("item", "college_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column("claim", "college_id", existing_type=sa.Integer(), nullable=False)
    op.create_index("uq_claim_one_active_per_item", "claim", ["item_id"], unique=True,
                    postgresql_where=sa.text("status IN ('pending', 'approved')"))


def downgrade():
    op.drop_index("uq_claim_one_active_per_item", "claim")
    op.alter_column("claim", "college_id", existing_type=sa.Integer(), nullable=True)
    op.alter_column("item", "college_id", existing_type=sa.Integer(), nullable=True)
