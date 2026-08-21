"""Tests for safe database schema migration and request verification."""

import importlib.util
import os
import sqlite3
import tempfile
import unittest


class TestDatabaseMigration(unittest.TestCase):
    """Verify that migrations are explicit, non-destructive, and not run on normal requests."""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_db.name
        self.temp_db.close()

        # Build raw legacy SQLite database (matching commit 5682d1f)
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE user (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email VARCHAR(120) NOT NULL UNIQUE,
            password VARCHAR(255) NOT NULL
        );
        """)
        cur.execute("""
        CREATE TABLE item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(120) NOT NULL,
            category VARCHAR(50),
            location VARCHAR(150),
            secret_detail TEXT,
            image_data TEXT,
            status VARCHAR(30) DEFAULT 'Available',
            date_found TIMESTAMP
        );
        """)
        cur.execute("""
        CREATE TABLE claim (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL REFERENCES item(id),
            student_id VARCHAR(50),
            student_email VARCHAR(120),
            phone VARCHAR(20),
            proof_description TEXT,
            timestamp TIMESTAMP
        );
        """)
        cur.execute("""
        INSERT INTO item (name, category, location, secret_detail, status, date_found)
        VALUES ('Legacy Laptop Bag', 'Accessories', 'Main Gate', 'Secret PIN on tag', 'Available', '2026-01-01 12:00:00');
        """)
        conn.commit()
        conn.close()

        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        os.environ["SECRET_KEY"] = "migration-test-secret"

        spec = importlib.util.spec_from_file_location("app_module", "app.py")
        self.app_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.app_module)

        self.app = self.app_module.app
        self.app.config["TESTING"] = True
        self.app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{self.db_path}"
        self.client = self.app.test_client()

    def tearDown(self):
        with self.app.app_context():
            self.app_module.db.session.remove()
            self.app_module.db.engine.dispose()
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except OSError:
                pass

    def test_migration_adds_missing_columns_and_preserves_data(self):
        with self.app.app_context():
            # Run explicit schema synchronization
            success = self.app_module.ensure_schema()
            self.assertTrue(success)

            # Query items using SQLAlchemy model with new item_type and ai_* columns
            items = self.app_module.Item.query.all()
            self.assertEqual(len(items), 1)
            legacy_item = items[0]

            self.assertEqual(legacy_item.name, "Legacy Laptop Bag")
            self.assertEqual(legacy_item.item_type, "found")
            self.assertEqual(legacy_item.status, "Available")
            self.assertEqual(legacy_item.secret_detail, "Secret PIN on tag")
            self.assertIsNone(legacy_item.ai_brand)

            # Check that item_match table was created
            match_count = self.app_module.ItemMatch.query.count()
            self.assertEqual(match_count, 0)

            # Verify idempotency: running ensure_schema a second time succeeds without errors
            second_success = self.app_module.ensure_schema()
            self.assertTrue(second_success)

    def test_no_unauthenticated_init_db_endpoint_exists(self):
        # Verify /init-db is completely removed (returns 404)
        resp = self.client.get("/init-db")
        self.assertEqual(resp.status_code, 404)

    def test_normal_requests_work_after_migration(self):
        with self.app.app_context():
            self.app_module.ensure_schema()

        # Accessing GET / renders index.html cleanly
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Legacy Laptop Bag", resp.data)


if __name__ == "__main__":
    unittest.main()
