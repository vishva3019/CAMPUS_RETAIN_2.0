"""Tests for AI Claim Verification Assistance (Phase 6)."""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from ai.claims import (
    analyze_claim,
    compute_deterministic_claim_score,
    evaluate_claim_with_ai,
)


class TestClaimDeterministicLogic(unittest.TestCase):
    """Test deterministic claim proof comparison rules and safety."""

    def test_high_confidence_matching_claim(self):
        item = {
            "name": "Black Nike Backpack",
            "category": "Accessories",
            "ai_category": "backpack",
            "ai_primary_color": "black",
            "ai_brand": "Nike",
            "ai_distinctive_features": ["red zipper"],
            "secret_detail": "Red zipper on front pocket",
        }
        claim = {
            "proof_description": "I lost my black Nike backpack, it has a red zipper on the front pocket.",
        }

        score, conf, matches, conflicts, expl = compute_deterministic_claim_score(
            claim, item
        )
        self.assertGreaterEqual(score, 80)
        self.assertEqual(conf, "high")
        self.assertTrue(len(matches) >= 3)
        self.assertEqual(len(conflicts), 0)
        self.assertTrue(any("secret" in m.lower() for m in matches))

    def test_low_confidence_conflicting_claim(self):
        item = {
            "name": "Black Nike Backpack",
            "category": "Accessories",
            "ai_category": "backpack",
            "ai_primary_color": "black",
            "ai_brand": "Nike",
            "secret_detail": "Contains student ID card inside",
        }
        claim = {
            "proof_description": "My blue Adidas bag that I left in the gym.",
        }

        score, conf, matches, conflicts, expl = compute_deterministic_claim_score(
            claim, item
        )
        self.assertLess(score, 60)
        self.assertEqual(conf, "low")
        self.assertTrue(len(conflicts) >= 1)
        self.assertTrue(any("color" in c.lower() or "brand" in c.lower() for c in conflicts))

    def test_missing_optional_information_is_neutral(self):
        item = {
            "name": "Nike Backpack",
            "category": "Accessories",
            "ai_category": "backpack",
            "ai_primary_color": "black",
            "ai_brand": "Nike",
        }
        claim = {
            "proof_description": "I lost my black backpack near the library.",
        }

        score, conf, matches, conflicts, expl = compute_deterministic_claim_score(
            claim, item
        )
        # Missing brand in claim is not treated as a conflict
        self.assertNotIn("Brand conflict", str(conflicts))
        self.assertGreaterEqual(score, 60)

    def test_secret_detail_not_exposed_in_factors(self):
        secret_string = "SUPER_SECRET_ENGRAVING_12345"
        item = {
            "name": "Metal Flask",
            "category": "Water Bottles",
            "secret_detail": secret_string,
        }
        claim = {
            "proof_description": "Blue flask",
        }

        score, conf, matches, conflicts, expl = compute_deterministic_claim_score(
            claim, item
        )
        # Ensure secret raw string is never dumped directly into matching/conflicting factors
        self.assertNotIn(secret_string, str(matches))
        self.assertNotIn(secret_string, str(conflicts))
        self.assertNotIn(secret_string, expl)


class TestClaimAIEvaluationAndFallback(unittest.TestCase):
    """Test AI evaluation, safety recommendations, and fallback."""

    def test_analyze_claim_recommendation_is_always_manual_review(self):
        item = {"name": "Casio Calculator", "category": "Electronics"}
        claim = {"proof_description": "Casio scientific calculator"}

        with patch.dict(os.environ, {"AI_PROVIDER": "mock", "AI_API_KEY": "test"}, clear=True):
            res = analyze_claim(claim, item)
            self.assertTrue(res["success"])
            data = res["data"]
            self.assertEqual(data["recommendation"], "manual_review")
            self.assertIn(data["confidence_level"], ("high", "medium", "low"))

    def test_ai_failure_fallback(self):
        item = {"name": "Black Backpack", "category": "Accessories"}
        claim = {"proof_description": "Black backpack"}

        with patch.dict(os.environ, {"AI_PROVIDER": "google", "AI_API_KEY": "test"}, clear=True):
            with patch("requests.post", side_effect=Exception("Timeout")):
                res = analyze_claim(claim, item)
                self.assertTrue(res["success"])
                self.assertEqual(res["data"]["recommendation"], "manual_review")
                self.assertGreaterEqual(res["data"]["confidence_score"], 40)


class TestFlaskClaimIntegration(unittest.TestCase):
    """Test Flask claim workflow and admin assistance endpoints."""

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

    def test_claim_submission_triggers_ai_verification(self):
        with self.app.app_context():
            item = self.app_module.Item(
                name="Black Nike Backpack",
                category="Accessories",
                location="Library",
                item_type="found",
                status="Available",
                ai_category="backpack",
                ai_primary_color="black",
                ai_brand="Nike",
                secret_detail="Red zipper",
            )
            self.app_module.db.session.add(item)
            self.app_module.db.session.commit()
            item_id = item.id

        with self.client.session_transaction() as sess:
            sess["user_email"] = "student@ced.alliance.edu.in"

        resp = self.client.post(
            "/api/claim",
            json={
                "item_id": item_id,
                "student_id": "CED2026-001",
                "student_email": "student@ced.alliance.edu.in",
                "phone": "9876543210",
                "proof_description": "My black Nike backpack with red zipper on front.",
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "success")
        claim_id = data["claim_id"]

        # Verify claim assessment endpoint
        assess_resp = self.client.get(f"/api/ai/claim-assessment/{claim_id}")
        self.assertEqual(assess_resp.status_code, 200)
        a_data = assess_resp.get_json()
        self.assertTrue(a_data["success"])
        self.assertGreaterEqual(a_data["data"]["confidence_score"], 80)
        self.assertEqual(a_data["data"]["confidence_level"], "high")
        self.assertEqual(a_data["data"]["recommendation"], "manual_review")

    def test_legacy_claim_record_compatibility(self):
        with self.app.app_context():
            item = self.app_module.Item(name="Keys", category="Keys", location="Gate", item_type="found", status="Pending")
            self.app_module.db.session.add(item)
            self.app_module.db.session.commit()

            # Legacy claim with NULL ai_* columns
            legacy_claim = self.app_module.Claim(
                item_id=item.id,
                student_id="CED2024-999",
                student_email="legacy@ced.alliance.edu.in",
                phone="9999999999",
                proof_description="Brass key",
            )
            self.app_module.db.session.add(legacy_claim)
            self.app_module.db.session.commit()
            cid = legacy_claim.id

        with self.client.session_transaction() as sess:
            sess["user_email"] = "student@ced.alliance.edu.in"

        # Endpoint gracefully computes assessment for legacy claims
        resp = self.client.get(f"/api/ai/claim-assessment/{cid}")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertIsNotNone(data["data"]["confidence_score"])


if __name__ == "__main__":
    unittest.main()
