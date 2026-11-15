"""Phase 7: PostgreSQL row-level security on college-owned tables.

Policies allow everything when app.college_id is unset (platform admin, CLI, migrations)
and only the signed-in college's rows otherwise. They only bind a role without
superuser/BYPASSRLS; see docs/DEPLOYMENT.md for the app role on Neon.

Revision ID: 0007_rls
Revises: 0006_network_events_tags
Create Date: 2026-11-14
"""
from alembic import op

from campus_retain.rls import install_rls, uninstall_rls

revision = "0007_rls"
down_revision = "0006_network_events_tags"
branch_labels = None
depends_on = None


def upgrade():
    install_rls(op.get_bind())


def downgrade():
    uninstall_rls(op.get_bind())
