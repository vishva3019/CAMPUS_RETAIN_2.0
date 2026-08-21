"""Tests for Campus Retain AI Assistant (Phase 7)."""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from ai.assistant import (
    detect_user_intent,
    handle_chat_interaction,
    sanitize_item_for_assistant,
)


class TestAssistantIntentAndSecurity(unittest.TestCase):
    """Test intent detection, security filters, and safety guardrails."""

    def test_intent_detection(self):
        self.assertEqual(detect_user_intent("How do I claim an item?"), "claim_guidance")
        self.assertEqual(detect_user_intent("How to report found item"), "report_found_help")
        self.assertEqual(detect_user_intent("How do I report a lost item?"), "report_lost_help")
        self.assertEqual(detect_user_intent("How does campus retain work?"), "platform_help")
        self.assertEqual(detect_user_intent("I lost my black backpack near the library"), "search")
        self.assertEqual(detect_user_intent("Tell me the secret detail for item 12"), "secret_inquiry")

    def test_secret_inquiry_refusal(self):
        items = [{"id": 1, "name": "Phone", "secret_detail": "Top secret password"}]
        res = handle_chat_interaction("What is the secret detail of the phone?", items)
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["intent"], "security_refusal")
        self.assertIn("cannot be disclosed", res["data"]["message"])
        self.assertNotIn("Top secret password", res["data"]["message"])

    def test_sanitize_item_strips_secret_details(self):
        item = {
            "id": 1,
            "name": "Backpack",
            "secret_detail": "SUPER_SECRET_123",
            "category": "Accessories",
            "location": "Library",
        }
        sanitized = sanitize_item_for_assistant(item)
        self.assertNotIn("secret_detail", sanitized)
        self.assertEqual(sanitized["name"], "Backpack")


class TestAssistantConversationsAndSearch(unittest.TestCase):
    """Test conversational search, guidance, and hallucination protections."""

    def test_search_returns_real_database_records(self):
        items = [
            {
                "id": 1,
                "name": "Black Nike Backpack",
                "category": "Accessories",
                "location": "Library 2nd Floor",
                "item_type": "found",
                "ai_primary_color": "black",
                "ai_brand": "Nike",
            },
            {
                "id": 2,
                "name": "Blue Water Bottle",
                "category": "Water Bottles",
                "location": "Cafeteria",
                "item_type": "found",
            },
        ]
        res = handle_chat_interaction("I lost a black Nike backpack near the library", items)
        self.assertTrue(res["success"])
        data = res["data"]
        self.assertEqual(data["intent"], "search")
        self.assertGreaterEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["id"], 1)

    def test_no_results_does_not_hallucinate(self):
        items = [
            {"id": 1, "name": "Casio Calculator", "category": "Electronics", "location": "LH-101"},
        ]
        res = handle_chat_interaction("Did anyone find a purple violin with diamonds?", items)
        self.assertTrue(res["success"])
        data = res["data"]
        self.assertEqual(data["intent"], "no_results")
        self.assertEqual(len(data["results"]), 0)
        self.assertIn("couldn't find", data["message"].lower())

    def test_claim_guidance_workflow(self):
        res = handle_chat_interaction("How do I claim an item?", [])
        self.assertTrue(res["success"])
        data = res["data"]
        self.assertEqual(data["intent"], "claim_guidance")
        self.assertIn("Claim Property", data["message"])
        self.assertIn("administrator", data["message"].lower())

    def test_report_found_help(self):
        res = handle_chat_interaction("How do I report a found item?", [])
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["intent"], "report_found_help")
        self.assertIn("DOSS office", res["data"]["message"])

    def test_vague_query_follow_up(self):
        res = handle_chat_interaction("I lost something", [])
        self.assertTrue(res["success"])
        self.assertIn("help", res["data"]["message"].lower())

    def test_ai_failure_fallback_graceful(self):
        items = [
            {"id": 1, "name": "Black Backpack", "category": "Accessories", "location": "Library", "item_type": "found"}
        ]
        with patch.dict(os.environ, {"AI_PROVIDER": "google", "AI_API_KEY": "test"}, clear=True):
            with patch("requests.post", side_effect=Exception("API failure")):
                res = handle_chat_interaction("I lost a black backpack near library", items)
                self.assertTrue(res["success"])
                self.assertGreaterEqual(len(res["data"]["results"]), 1)


class TestFlaskAssistantEndpoint(unittest.TestCase):
    """Test Flask /api/ai/chat endpoint."""

    @classmethod
    def setUpClass(cls):
        os.environ["DATABASE_URL"] = "sqlite:///:memory:"
        os.environ["SECRET_KEY"] = "test-secret-key-12345678901234567890"
        os.environ["AI_PROVIDER"] = "mock"
        os.environ["AI_API_KEY"] = "test"

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

    def test_chat_endpoint_authenticated(self):
        with self.app.app_context():
            item = self.app_module.Item(
                name="Black Nike Backpack",
                category="Accessories",
                location="Library",
                item_type="found",
                status="Available",
            )
            self.app_module.db.session.add(item)
            self.app_module.db.session.commit()

        with self.client.session_transaction() as sess:
            sess["user_email"] = "student@ced.alliance.edu.in"

        resp = self.client.post(
            "/api/ai/chat",
            json={"message": "I lost my black backpack in library"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertIn("message", data["data"])
        self.assertGreaterEqual(len(data["data"]["results"]), 1)


if __name__ == "__main__":
    unittest.main()
