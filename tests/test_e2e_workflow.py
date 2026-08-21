"""End-to-End User Lifecycle & AI Workflow Tests (Final QA)."""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch


class TestCampusRetainE2EWorkflow(unittest.TestCase):
    """Full end-to-end lifecycle integration testing."""

    @classmethod
    def setUpClass(cls):
        os.environ["DATABASE_URL"] = "sqlite:///:memory:"
        os.environ["SECRET_KEY"] = "e2e-secret-key-12345678901234567890"
        os.environ["AI_PROVIDER"] = "mock"
        os.environ["AI_API_KEY"] = "mock-key"
        os.environ["ADMIN_EMAIL"] = "admin@ced.alliance.edu.in"
        os.environ["ADMIN_PASSWORD"] = "AdminPass123!"

        import importlib.util
        spec = importlib.util.spec_from_file_location("app_module", "app.py")
        cls.app_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.app_module)
        cls.app = cls.app_module.app
        cls.app.config["TESTING"] = True

    def setUp(self):
        self.client = self.app.test_client()
        with self.app.app_context():
            self.app_module.db.create_all()

    def tearDown(self):
        with self.app.app_context():
            self.app_module.db.session.remove()
            self.app_module.db.drop_all()

    def test_complete_student_and_admin_ai_journey(self):
        # 1. Student Registration & Authentication
        reg_resp = self.client.post(
            "/login",
            data={"email": "student@ced.alliance.edu.in", "password": "StudentPassword123!"},
        )
        self.assertEqual(reg_resp.status_code, 302)

        # 2. Staff reports a Found Item with AI Metadata
        with self.client.session_transaction() as sess:
            sess["user_email"] = "staff@ced.alliance.edu.in"

        ai_meta = {
            "category": "backpack",
            "primary_color": "black",
            "secondary_colors": ["red"],
            "brand": "Nike",
            "model": "Elemental",
            "distinctive_features": ["red zipper on front pocket"],
            "condition": "good",
            "confidence": 0.92,
        }

        found_resp = self.client.post(
            "/api/report",
            data={
                "name": "Black Nike Backpack",
                "category": "Accessories",
                "location": "Library 2nd Floor",
                "secret_detail": "Red zipper on front pocket with keychain",
                "ai_metadata": json.dumps(ai_meta),
            },
        )
        self.assertEqual(found_resp.status_code, 200)

        # 3. Student searches for the lost backpack using Natural Language
        with self.client.session_transaction() as sess:
            sess["user_email"] = "student@ced.alliance.edu.in"

        search_resp = self.client.post(
            "/api/ai/search",
            json={"query": "I lost my black Nike backpack near the library yesterday"},
        )
        self.assertEqual(search_resp.status_code, 200)
        s_data = search_resp.get_json()
        self.assertTrue(s_data["success"])
        self.assertGreaterEqual(len(s_data["data"]["results"]), 1)
        found_item_id = s_data["data"]["results"][0]["id"]
        self.assertEqual(s_data["data"]["results"][0]["name"], "Black Nike Backpack")
        self.assertGreaterEqual(s_data["data"]["results"][0]["relevance_score"], 80)

        # 4. Student reports the Lost Item to discover automatic matches
        lost_resp = self.client.post(
            "/api/report-lost",
            data={
                "name": "Black Nike Backpack",
                "category": "Accessories",
                "location": "Library",
                "secret_detail": "Red zipper on front pocket",
                "ai_metadata": json.dumps({
                    "category": "backpack",
                    "primary_color": "black",
                    "brand": "Nike",
                    "distinctive_features": ["red zipper on front pocket"],
                }),
            },
        )
        self.assertEqual(lost_resp.status_code, 200)
        l_data = lost_resp.get_json()
        self.assertEqual(l_data["status"], "success")
        self.assertGreaterEqual(l_data["match_count"], 1)

        # 5. Student submits a Claim for the found item
        claim_resp = self.client.post(
            "/api/claim",
            json={
                "item_id": found_item_id,
                "student_id": "CED2026-888",
                "student_email": "student@ced.alliance.edu.in",
                "phone": "9876543210",
                "proof_description": "My black Nike bag with red zipper on front pocket containing key.",
            },
        )
        self.assertEqual(claim_resp.status_code, 200)
        claim_id = claim_resp.get_json()["claim_id"]

        # 6. Verify AI Claim Verification Assessment
        assess_resp = self.client.get(f"/api/ai/claim-assessment/{claim_id}")
        self.assertEqual(assess_resp.status_code, 200)
        ass_data = assess_resp.get_json()
        self.assertTrue(ass_data["success"])
        self.assertEqual(ass_data["data"]["confidence_level"], "high")
        self.assertEqual(ass_data["data"]["recommendation"], "manual_review")

        # 7. Student uses Campus Retain AI Assistant in chat
        chat_resp = self.client.post(
            "/api/ai/chat",
            json={"message": "Can you help me find my black backpack near library?"},
        )
        self.assertEqual(chat_resp.status_code, 200)
        c_data = chat_resp.get_json()
        self.assertTrue(c_data["success"])
        self.assertGreaterEqual(len(c_data["data"]["results"]), 1)

        # 8. Admin reviews and approves the claim
        with self.client.session_transaction() as sess:
            sess["is_admin"] = True

        approve_resp = self.client.post(f"/api/admin/approve/{found_item_id}")
        self.assertEqual(approve_resp.status_code, 200)

        # Verify item status is now Claimed
        with self.app.app_context():
            item = self.app_module.db.session.get(self.app_module.Item, found_item_id)
            self.assertEqual(item.status, "Claimed")


if __name__ == "__main__":
    unittest.main()
