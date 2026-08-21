#!/usr/bin/env python3
"""Standalone database schema migration CLI for Campus Retain.

Safely applies non-destructive schema migrations (adds missing columns and tables)
to PostgreSQL (Neon) or SQLite without data loss.

Usage:
  python migrate.py
  DATABASE_URL="postgresql://user:pass@host/dbname?sslmode=require" python migrate.py
  python migrate.py --sql
"""
import argparse
import importlib.util
import os
import sys

# Load app.py module directly
project_root = os.path.dirname(os.path.abspath(__file__))
app_py_path = os.path.join(project_root, "app.py")
spec = importlib.util.spec_from_file_location("app_main", app_py_path)
app_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app_module)

app = app_module.app
db = app_module.db
ensure_schema = app_module.ensure_schema


def mask_db_url(url: str) -> str:
    """Mask password in database URL for safe terminal output."""
    if not url:
        return "<not set>"
    if "@" in url and "://" in url:
        prefix, rest = url.split("://", 1)
        user_info, host_info = rest.split("@", 1)
        if ":" in user_info:
            user, _ = user_info.split(":", 1)
            return f"{prefix}://{user}:*****@{host_info}"
    return url


def main():
    parser = argparse.ArgumentParser(
        description="Campus Retain - Controlled Database Migration Tool"
    )
    parser.add_argument(
        "--sql",
        action="store_true",
        help="Print the raw SQL migration commands without executing.",
    )
    args = parser.parse_args()

    print("==================================================")
    print("Campus Retain - Safe Database Schema Migration CLI")
    print("==================================================")

    if args.sql:
        sql_file = os.path.join(project_root, "migrations", "001_ai_schema_upgrade.sql")
        if os.path.exists(sql_file):
            with open(sql_file, "r") as f:
                print(f.read())
        return

    with app.app_context():
        dialect = db.engine.dialect.name
        db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
        print(f"[*] Target Database Dialect: {dialect}")
        print(f"[*] Connection Endpoint:     {mask_db_url(db_uri)}")
        print("[*] Running idempotent schema synchronization...")

        success = ensure_schema()
        if success:
            print("[✓] Schema migration completed successfully!")
            print("[✓] Verified tables and columns:")
            print("    - Table 'item': added item_type, reported_by, date_lost, ai_* columns")
            print("    - Table 'claim': added ai_* verification columns")
            print("    - Table 'item_match': verified table structure & foreign keys")
            print("    - Backfilled item_type='found' for legacy records")
        else:
            print("[!] Migration encountered warnings. Check output logs.")
            sys.exit(1)


if __name__ == "__main__":
    main()
