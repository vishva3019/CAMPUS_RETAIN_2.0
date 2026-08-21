"""Comprehensive security and authorization verification tests."""

import importlib.util
import json
import os
import tempfile
import unittest


class TestSecurityAuthorization(unittest.TestCase):
    """Test security boundaries, public vs authenticated endpoints, and anti-leak safeguards."""

    @classmethod
    def setUpClass(cls):
        cls.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls.db_path = cls.temp_db.name
        cls.temp_db.close()

        os.environ["DATABASE_URL"] = f"sqlite:///{cls.db_path}"
        os.environ["SECRET_KEY"] = "security-test-secret"
        os.environ["AI_PROVIDER"] = "mock"
        os.environ["AI_API_KEY"] = "test-key"

        spec = importlib.util.spec_from_file_location("app_main", "app.py")
        cls.app_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.app_module)

        cls.app = cls.app_module.app
        cls.app.config["TESTING"] = True

    def setUp(self):
        self.client = self.app.test_client()
        with self.app.app_context():
            self.app_module.ensure_schema()
            # Seed test item with secret detail
            self.item = self.app_module.Item(
                name="Black Leather Wallet",
                category="Accessories",
                location="Main Auditorium",
                secret_detail="SECRET_CARD_PIN_8842",
                item_type="found",
                status="Available",
                ai_category="wallet",
                ai_primary_color="black",
            )
            self.app_module.db.session.add(self.item)
            self.app_module.db.session.commit()
            self.item_id = self.item.id

    def tearDown(self):
        with self.app.app_context():
            self.app_module.db.session.remove()
            self.app_module.db.drop_all()

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.db_path):
            try:
                os.remove(cls.db_path)
            except OSError:
                pass

    # 1. GET / -> 200
    def test_homepage_is_public(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)

    # 2. Public AI chat -> 200
    def test_public_ai_chat_returns_200_without_login(self):
        resp = self.client.post("/api/ai/chat", json={"message": "How do I claim an item?"})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["intent"], "claim_guidance")

    # 3. Public AI search -> 200
    def test_public_ai_search_returns_200_without_login(self):
        resp = self.client.post("/api/ai/search", json={"query": "black wallet"})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        # Verify secret detail is NOT leaked in search results
        results_str = json.dumps(data)
        self.assertNotIn("SECRET_CARD_PIN_8842", results_str)

    # 4. Public AI matches -> 200 (sanitized)
    def test_public_ai_matches_returns_200_without_secret_leak(self):
        resp = self.client.get(f"/api/ai/matches/{self.item_id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertNotIn("SECRET_CARD_PIN_8842", json.dumps(data))

    # 5. AI Image Analysis requires authentication -> 401 when unauthenticated
    def test_unauthenticated_image_analysis_returns_401(self):
        resp = self.client.post(
            "/api/ai/analyze-image",
            json={"image": "data:image/jpeg;base64,mockimagedata"},
        )
        self.assertEqual(resp.status_code, 401)
        data = resp.get_json()
        self.assertFalse(data["success"])
        self.assertIn("Authentication required", data["error"])

    # 6. Authenticated student can use AI Image Analysis
    def test_authenticated_image_analysis_returns_200(self):
        with self.client.session_transaction() as sess:
            sess["user_email"] = "student@ced.alliance.edu.in"

        valid_b64 = "data:image/jpeg;base64," + "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        resp = self.client.post(
            "/api/ai/analyze-image",
            json={"image": valid_b64},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertIn("category", data["data"])

    # 7. Unauthenticated claim submission is rejected -> 401
    def test_unauthenticated_claim_submission_rejected(self):
        resp = self.client.post(
            "/api/claim",
            json={
                "item_id": self.item_id,
                "student_id": "ST123",
                "phone": "9876543210",
                "proof_description": "My black wallet with cards",
            },
        )
        self.assertEqual(resp.status_code, 401)

    # 8. Unauthenticated admin action is rejected -> 403
    def test_unauthenticated_admin_approval_rejected(self):
        resp = self.client.post(f"/api/admin/approve/{self.item_id}")
        self.assertEqual(resp.status_code, 403)

    # 9. AI claim verification is protected -> 401 (unauthenticated)
    def test_unauthenticated_claim_verification_rejected(self):
        resp = self.client.post(f"/api/ai/analyze-claim/1")
        self.assertIn(resp.status_code, [401, 403])

    # 10. Admin functions work with admin session
    def test_authenticated_admin_approval_succeeds(self):
        with self.client.session_transaction() as sess:
            sess["is_admin"] = True

        resp = self.client.post(f"/api/admin/approve/{self.item_id}")
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()
