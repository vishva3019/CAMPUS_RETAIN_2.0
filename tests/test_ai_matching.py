"""Tests for AI Lost & Found Matching Engine (Phase 4)."""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import MagicMock, patch

from ai.exceptions import AIError, AIProviderError
from ai.matching import (
    _are_colors_similar,
    compute_deterministic_match_score,
    evaluate_match_with_ai,
    find_potential_matches,
)


class TestMatchingDeterministicLogic(unittest.TestCase):
    """Test deterministic attribute comparisons and scoring logic."""

    def test_color_family_similarity(self):
        # Exact match
        exact, similar = _are_colors_similar("black", "black")
        self.assertTrue(exact)
        self.assertTrue(similar)

        # Color family match
        exact, similar = _are_colors_similar("navy", "blue")
        self.assertFalse(exact)
        self.assertTrue(similar)

        # Completely different colors
        exact, similar = _are_colors_similar("red", "green")
        self.assertFalse(exact)
        self.assertFalse(similar)

    def test_strong_match(self):
        lost_item = {
            "name": "Black Nike Backpack",
            "category": "Accessories",
            "location": "Library 2nd Floor",
            "ai_category": "backpack",
            "ai_primary_color": "black",
            "ai_brand": "Nike",
            "ai_distinctive_features": ["red zipper", "white swoosh"],
            "date_found": "2026-08-20T10:00:00",
        }
        found_item = {
            "name": "Black Nike Backpack",
            "category": "Accessories",
            "location": "Library 2nd Floor",
            "ai_category": "backpack",
            "ai_primary_color": "black",
            "ai_brand": "Nike",
            "ai_distinctive_features": ["red zipper", "white swoosh"],
            "date_found": "2026-08-20T14:00:00",
        }

        score, conf, matches, diffs, expl = compute_deterministic_match_score(
            lost_item, found_item
        )
        self.assertGreaterEqual(score, 80)
        self.assertEqual(conf, "high")
        self.assertTrue(any("category" in m.lower() for m in matches))
        self.assertTrue(any("color" in m.lower() for m in matches))
        self.assertTrue(any("brand" in m.lower() for m in matches))

    def test_partial_match(self):
        lost_item = {
            "name": "Black Backpack",
            "category": "Accessories",
            "location": "Library Block A",
            "ai_category": "backpack",
            "ai_primary_color": "black",
            "date_found": "2026-08-15T10:00:00",
        }
        found_item = {
            "name": "Black Backpack",
            "category": "Accessories",
            "location": "Food Court Cafeteria",
            "ai_category": "backpack",
            "ai_primary_color": "black",
            "date_found": "2026-08-20T14:00:00",
        }

        score, conf, matches, diffs, expl = compute_deterministic_match_score(
            lost_item, found_item
        )
        self.assertGreaterEqual(score, 50)
        self.assertLess(score, 85)
        self.assertTrue(any("location" in d.lower() for d in diffs))

    def test_unrelated_different_items(self):
        lost_item = {
            "name": "Blue Hydro Flask Water Bottle",
            "category": "Water Bottles",
            "location": "Sports Complex",
            "ai_category": "water bottle",
            "ai_primary_color": "blue",
            "ai_brand": "Hydro Flask",
        }
        found_item = {
            "name": "Black Lenovo ThinkPad Laptop",
            "category": "Electronics",
            "location": "Engineering Lab 3",
            "ai_category": "laptop",
            "ai_primary_color": "black",
            "ai_brand": "Lenovo",
        }

        score, conf, matches, diffs, expl = compute_deterministic_match_score(
            lost_item, found_item
        )
        self.assertLess(score, 40)
        self.assertEqual(conf, "low")


class TestAIReasoningAndFallback(unittest.TestCase):
    """Test LLM semantic evaluation and fallback handling."""

    def test_evaluate_with_ai_mock_provider(self):
        lost = {"name": "Black Backpack", "category": "Accessories"}
        found = {"name": "Black Backpack", "category": "Accessories"}

        with patch.dict(os.environ, {"AI_PROVIDER": "mock", "AI_API_KEY": "test"}, clear=True):
            res = evaluate_match_with_ai(
                lost, found, 75, "medium", ["Same category"], [], "Baseline explanation"
            )
            self.assertIn("match_score", res)
            self.assertIn("confidence", res)
            self.assertIn("matching_attributes", res)
            self.assertIn("explanation", res)

    def test_evaluate_with_ai_failure_fallback(self):
        lost = {"name": "Black Backpack"}
        found = {"name": "Black Backpack"}

        with patch.dict(os.environ, {"AI_PROVIDER": "google", "AI_API_KEY": "test"}, clear=True):
            with patch("requests.post", side_effect=Exception("API network timeout")):
                res = evaluate_match_with_ai(
                    lost, found, 70, "medium", ["Same category"], ["Diff location"], "Baseline explanation"
                )
                self.assertEqual(res["match_score"], 70)
                self.assertEqual(res["confidence"], "medium")
                self.assertEqual(res["explanation"], "Baseline explanation")

    def test_find_potential_matches_filters_and_ranks(self):
        target_lost = {
            "id": 1,
            "name": "Black Nike Backpack",
            "category": "Accessories",
            "location": "Library",
            "ai_category": "backpack",
            "ai_primary_color": "black",
            "ai_brand": "Nike",
        }

        candidates = [
            {
                "id": 10,
                "name": "Black Nike Backpack",
                "category": "Accessories",
                "location": "Library",
                "ai_category": "backpack",
                "ai_primary_color": "black",
                "ai_brand": "Nike",
            },
            {
                "id": 11,
                "name": "Blue Water Bottle",
                "category": "Water Bottles",
                "location": "Cafeteria",
                "ai_category": "water bottle",
                "ai_primary_color": "blue",
            },
            {
                "id": 12,
                "name": "Grey Bag",
                "category": "Accessories",
                "location": "Block 2",
                "ai_category": "backpack",
                "ai_primary_color": "grey",
            },
        ]

        res = find_potential_matches(target_lost, candidates)
        self.assertTrue(res["success"])
        matches = res["data"]["matches"]
        self.assertTrue(len(matches) >= 1)
        # Top candidate must be the strong match (#10)
        self.assertEqual(matches[0]["candidate_id"], 10)
        self.assertGreaterEqual(matches[0]["match_score"], 75)


class TestFlaskMatchingIntegration(unittest.TestCase):
    """Test Flask endpoints for lost item reporting, match retrieval, and syncing."""

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

    def test_report_lost_and_match_discovery_workflow(self):
        # 1. First, create a Found item in the database
        with self.app.app_context():
            found_item = self.app_module.Item(
                name="Black Nike Backpack",
                category="Accessories",
                location="Library 2nd Floor",
                item_type="found",
                status="Available",
                ai_category="backpack",
                ai_primary_color="black",
                ai_brand="Nike",
                ai_distinctive_features=["red zipper"],
            )
            self.app_module.db.session.add(found_item)
            self.app_module.db.session.commit()
            found_id = found_item.id

        # 2. Student logs in and reports a Lost item
        with self.client.session_transaction() as sess:
            sess["user_email"] = "student@ced.alliance.edu.in"

        resp = self.client.post(
            "/api/report-lost",
            data={
                "name": "Black Nike Backpack",
                "category": "Accessories",
                "location": "Library",
                "secret_detail": "Has red zipper on front pocket",
                "ai_metadata": json.dumps({
                    "category": "backpack",
                    "primary_color": "black",
                    "brand": "Nike",
                    "distinctive_features": ["red zipper"],
                }),
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "success")
        lost_id = data["item_id"]

        # 3. Check discovered matches endpoint
        matches_resp = self.client.get(f"/api/ai/matches/{lost_id}")
        self.assertEqual(matches_resp.status_code, 200)
        m_data = matches_resp.get_json()
        self.assertTrue(m_data["success"])
        self.assertGreaterEqual(len(m_data["data"]["matches"]), 1)

        match_entry = m_data["data"]["matches"][0]
        self.assertEqual(match_entry["matched_item_id"], found_id)
        self.assertGreaterEqual(match_entry["match_score"], 75)

    def test_duplicate_analysis_updates_rather_than_duplicates(self):
        with self.app.app_context():
            lost_item = self.app_module.Item(
                name="Casio FX-991EX Calculator",
                category="Electronics",
                location="LH-101",
                item_type="lost",
                status="Active",
            )
            found_item = self.app_module.Item(
                name="Casio Calculator",
                category="Electronics",
                location="LH-102",
                item_type="found",
                status="Available",
            )
            self.app_module.db.session.add_all([lost_item, found_item])
            self.app_module.db.session.commit()

            # Run sync twice
            self.app_module.sync_item_matches(lost_item)
            self.app_module.sync_item_matches(lost_item)

            # Check that only 1 record exists in ItemMatch table
            matches_count = self.app_module.ItemMatch.query.filter_by(
                lost_item_id=lost_item.id, found_item_id=found_item.id
            ).count()
            self.assertEqual(matches_count, 1)

    def test_legacy_records_compatibility(self):
        """Verify that legacy items with NULL item_type and NULL AI fields operate safely."""
        with self.app.app_context():
            legacy_item = self.app_module.Item(
                name="Keys on lanyard",
                category="Keys",
                location="Main Gate",
                item_type=None,
                status="Available",
            )
            self.app_module.db.session.add(legacy_item)
            self.app_module.db.session.commit()

            # Ensure to_dict handles null item_type
            d = legacy_item.to_dict()
            self.assertEqual(d["item_type"], "found")

            # Check matching against legacy item
            target_lost = {
                "name": "Keys with red lanyard",
                "category": "Keys",
                "location": "Main Gate",
            }
            score, conf, matches, diffs, expl = compute_deterministic_match_score(target_lost, d)
            self.assertGreaterEqual(score, 40)


if __name__ == "__main__":
    unittest.main()

