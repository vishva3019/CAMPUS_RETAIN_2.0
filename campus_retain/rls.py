"""PostgreSQL Row-Level Security: a second isolation layer under tenant_query.

Every transaction sets ``app.college_id`` (transaction-local) to the signed-in user's
college. Policies on college-owned tables then hide and refuse rows of other colleges,
even if application code forgets a filter.

The setting is empty (no restriction) for platform admins, signed-out pages, CLI
commands and migrations, and inside ``rls_bypass()``, which the inter-college network
uses for its deliberate, audited cross-college reads and claims.

RLS only applies to a database role that is not a superuser and has no BYPASSRLS.
On Neon, give the app its own restricted role (docs/DEPLOYMENT.md).
"""
from contextlib import contextmanager

from flask import g, has_app_context
from sqlalchemy import event, text
from sqlalchemy.orm import Session

# College-owned tables. Users, colleges, notifications, subscriptions and the audit log are
# left out on purpose: they are read across colleges by design (network claimants, plans)
# and are always filtered by user or college in the code.
RLS_TABLES = ("item", "claim", "item_image", "item_match", "collection_point", "event", "campus", "item_tag")

_SCOPE = "nullif(current_setting('app.college_id', true), '')"
POLICY_SQL = f"(coalesce(current_setting('app.college_id', true), '') = '' OR college_id = {_SCOPE}::int)"


def install_rls(conn):
    """Enable and force RLS with one isolation policy per table. Idempotent."""
    for table in RLS_TABLES:
        conn.execute(text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
        conn.execute(text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
        conn.execute(text(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"'))
        conn.execute(text(f'CREATE POLICY tenant_isolation ON "{table}" USING {POLICY_SQL} WITH CHECK {POLICY_SQL}'))


def uninstall_rls(conn):
    for table in RLS_TABLES:
        conn.execute(text(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"'))
        conn.execute(text(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY'))
        conn.execute(text(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY'))


def current_scope():
    # Uses a plain value captured once per request: reading g.user here could trigger a
    # lazy load while the session is still opening its connection.
    if not has_app_context() or g.get("rls_bypass"):
        return ""
    college_id = g.get("rls_college_id")
    return str(college_id) if college_id else ""


def _set(connection_or_session):
    connection_or_session.execute(text("SELECT set_config('app.college_id', :v, true)"), {"v": current_scope()})


def capture_scope():
    """Call once sign-in is resolved for the request."""
    user = g.get("user")
    g.rls_college_id = user.college_id if user is not None else None


def apply_scope():
    """Re-apply the scope to the current transaction (after sign-in is resolved)."""
    from .extensions import db
    if db.engine.dialect.name == "postgresql":
        _set(db.session)


@contextmanager
def rls_bypass():
    """Deliberate cross-college access (inter-college network). Keep the block small."""
    previous = g.get("rls_bypass", False)
    g.rls_bypass = True
    apply_scope()
    try:
        yield
    finally:
        g.rls_bypass = previous
        apply_scope()


_registered = False


def register(app):
    global _registered
    if _registered:
        return
    _registered = True

    @event.listens_for(Session, "after_begin")
    def _scope_new_transaction(session, transaction, connection):
        if connection.dialect.name == "postgresql":
            _set(connection)
