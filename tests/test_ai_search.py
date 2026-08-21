"""Tests for AI Natural Language Search (Phase 5)."""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import MagicMock, patch

from ai.search import (
    deterministic_parse_query,
    parse_natural_language_query,
    rank_search_results,
    semantic_search,
)


class TestQueryUnderstanding(unittest.TestCase):
    """Test natural language parsing and entity extraction."""

    def test_full_query_extraction_deterministic(self):
        query = "I lost a black Nike backpack near the library yesterday"
        parsed = deterministic_parse_query(query)
        self.assertEqual(parsed["category"], "backpack")
        self.assertEqual(parsed["primary_color"], "black")
        self.assertEqual(parsed["brand"], "Nike")
        self.assertEqual(parsed["location"], "Library")
        self.assertEqual(parsed["time_reference"], "yesterday")
        self.assertEqual(parsed["search_target"], "found")

    def test_minimal_query_no_hallucinations(self):
        query = "I lost my phone"
        parsed = deterministic_parse_query(query)
        self.assertEqual(parsed["category"], "smartphone")
        self.assertIsNone(parsed["brand"])
        self.assertIsNone(parsed["primary_color"])
        self.assertIsNone(parsed["location"])
        self.assertIsNone(parsed["time_reference"])
        self.assertEqual(parsed["search_target"], "found")

    def test_found_inquiry_query(self):
        query = "Has anyone found a blue water bottle near cafeteria?"
        parsed = deterministic_parse_query(query)
        self.assertEqual(parsed["category"], "water bottle")
        self.assertEqual(parsed["primary_color"], "blue")
        self.assertEqual(parsed["location"], "Cafeteria")
        self.assertEqual(parsed["search_target"], "found")

    def test_location_and_time_only_query(self):
        query = "I lost something near the cafeteria last week"
        parsed = deterministic_parse_query(query)
        self.assertEqual(parsed["location"], "Cafeteria")
        self.assertEqual(parsed["time_reference"], "last week")
        self.assertIsNone(parsed["primary_color"])
        self.assertIsNone(parsed["brand"])

    def test_ai_provider_parsing_with_mock(self):
        query = "I lost my silver MacBook in Engineering Lab"
        with patch.dict(os.environ, {"AI_PROVIDER": "mock", "AI_API_KEY": "test"}, clear=True):
            parsed = parse_natural_language_query(query)
            self.assertIn("category", parsed)
            self.assertIn("keywords", parsed)
            self.assertEqual(parsed["search_target"], "found")

    def test_ai_provider_failure_fallback_to_deterministic(self):
        query = "I lost a red wildcraft bag at sports complex"
        with patch.dict(os.environ, {"AI_PROVIDER": "google", "AI_API_KEY": "test"}, clear=True):
            with patch("requests.post", side_effect=Exception("API connection failure")):
                parsed = parse_natural_language_query(query)
                self.assertEqual(parsed["category"], "backpack")
                self.assertEqual(parsed["primary_color"], "red")
                self.assertEqual(parsed["brand"], "Wildcraft")
                self.assertEqual(parsed["location"], "Sports Complex")


class TestSearchRanking(unittest.TestCase):
    """Test candidate item ranking and relevance scoring."""

    def test_relevance_ranking_orders_strongest_first(self):
        query_understanding = {
            "category": "backpack",
            "primary_color": "black",
            "brand": "Nike",
            "location": "Library",
            "time_reference": "yesterday",
            "search_target": "found",
            "keywords": ["backpack", "black", "nike", "library"],
        }

        candidates = [
            {
                "id": 1,
                "name": "Blue Water Bottle",
                "category": "Water Bottles",
                "location": "Sports Complex",
                "ai_category": "water bottle",
                "ai_primary_color": "blue",
            },
            {
                "id": 2,
                "name": "Black Backpack",
                "category": "Accessories",
                "location": "Cafeteria",
                "ai_category": "backpack",
                "ai_primary_color": "black",
            },
            {
                "id": 3,
                "name": "Black Nike Backpack",
                "category": "Accessories",
                "location": "Library 2nd Floor",
                "ai_category": "backpack",
                "ai_primary_color": "black",
                "ai_brand": "Nike",
            },
        ]

        results = rank_search_results(query_understanding, candidates)
        self.assertGreaterEqual(len(results), 2)
        # Top result must be item #3 (exact brand, color, category, location)
        self.assertEqual(results[0]["id"], 3)
        self.assertGreaterEqual(results[0]["relevance_score"], 80)
        self.assertEqual(results[0]["relevance_label"], "High Relevance")
        self.assertTrue(any("Nike" in str(a) or "brand" in str(a).lower() for a in results[0]["matching_attributes"]))

    def test_empty_candidates_returns_empty_list(self):
        query_understanding = {"category": "laptop", "keywords": ["laptop"]}
        results = rank_search_results(query_understanding, [])
        self.assertEqual(results, [])

    def test_semantic_search_function_end_to_end(self):
        items = [
            {"id": 1, "name": "Apple iPhone 15", "category": "Electronics", "location": "Library", "item_type": "found"},
            {"id": 2, "name": "Casio Calculator", "category": "Electronics", "location": "LH-101", "item_type": "found"},
        ]
        res = semantic_search("I lost my iPhone in the library", items)
        self.assertTrue(res["success"])
        self.assertIn("query_understanding", res["data"])
        self.assertGreaterEqual(len(res["data"]["results"]), 1)
        self.assertEqual(res["data"]["results"][0]["id"], 1)


class TestFlaskSearchIntegration(unittest.TestCase):
    """Test Flask /api/ai/search endpoint."""

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

    def test_api_ai_search_endpoint_success(self):
        # Insert test items in DB
        with self.app.app_context():
            item1 = self.app_module.Item(
                name="Black Nike Backpack",
                category="Accessories",
                location="Library 2nd Floor",
                item_type="found",
                status="Available",
                ai_category="backpack",
                ai_primary_color="black",
                ai_brand="Nike",
            )
            item2 = self.app_module.Item(
                name="Blue Umbrella",
                category="Accessories",
                location="Main Gate",
                item_type="found",
                status="Available",
            )
            self.app_module.db.session.add_all([item1, item2])
            self.app_module.db.session.commit()

        # Login student
        with self.client.session_transaction() as sess:
            sess["user_email"] = "student@ced.alliance.edu.in"

        resp = self.client.post(
            "/api/ai/search",
            json={"query": "I lost my black Nike bag in the library", "target": "found"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertIn("query_understanding", data["data"])
        self.assertGreaterEqual(len(data["data"]["results"]), 1)
        self.assertEqual(data["data"]["results"][0]["name"], "Black Nike Backpack")

    def test_api_ai_search_empty_query(self):
        with self.client.session_transaction() as sess:
            sess["user_email"] = "student@ced.alliance.edu.in"

        resp = self.client.post("/api/ai/search", json={"query": "   "})
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data["success"])


if __name__ == "__main__":
    unittest.main()
