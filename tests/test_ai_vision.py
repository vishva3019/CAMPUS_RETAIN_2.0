"""Tests for AI Vision Image Analysis (Phase 3)."""

from __future__ import annotations

import base64
import json
import os
import unittest
from unittest.mock import MagicMock, patch

from ai.client import (
    GoogleGeminiProvider,
    MockAIProvider,
    OpenAIProvider,
    get_ai_client,
)
from ai.exceptions import (
    AIAuthenticationError,
    AIError,
    AIProviderError,
    AIRateLimitError,
    AITimeoutError,
)
from ai.vision import (
    analyze_item_image,
    normalize_ai_vision_output,
    sniff_image_mime,
    validate_and_extract_image_bytes,
)

# 1x1 Transparent PNG for valid test images
SAMPLE_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe"
    b"\xdc\xccY\xe7\x00\x00\x00\x00IEND\xaeB`\x82"
)

# Sample JPEG magic bytes + dummy data
SAMPLE_JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00" + b"\x00" * 30


class TestImageValidation(unittest.TestCase):
    """Test image format sniffing and byte extraction validation."""

    def test_sniff_png(self):
        result = sniff_image_mime(SAMPLE_PNG_BYTES[:32])
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "image/png")
        self.assertEqual(result[1], "png")

    def test_sniff_jpeg(self):
        result = sniff_image_mime(SAMPLE_JPEG_BYTES[:32])
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "image/jpeg")
        self.assertEqual(result[1], "jpg")

    def test_sniff_invalid_format(self):
        text_bytes = b"This is a text file not an image."
        self.assertIsNone(sniff_image_mime(text_bytes[:32]))

    def test_validate_valid_bytes(self):
        raw, mime, ext = validate_and_extract_image_bytes(SAMPLE_PNG_BYTES)
        self.assertEqual(raw, SAMPLE_PNG_BYTES)
        self.assertEqual(mime, "image/png")
        self.assertEqual(ext, "png")

    def test_validate_data_uri(self):
        b64 = base64.b64encode(SAMPLE_PNG_BYTES).decode("utf-8")
        data_uri = f"data:image/png;base64,{b64}"
        raw, mime, ext = validate_and_extract_image_bytes(data_uri)
        self.assertEqual(raw, SAMPLE_PNG_BYTES)
        self.assertEqual(mime, "image/png")

    def test_validate_empty_input(self):
        with self.assertRaises(AIError):
            validate_and_extract_image_bytes(None)
        with self.assertRaises(AIError):
            validate_and_extract_image_bytes(b"")

    def test_validate_oversized_image(self):
        huge_bytes = SAMPLE_PNG_BYTES + (b"0" * (6 * 1024 * 1024))
        with self.assertRaises(AIError):
            validate_and_extract_image_bytes(huge_bytes)


class TestVisionNormalization(unittest.TestCase):
    """Test normalization and sanitization of vision model outputs."""

    def test_normalize_complete_payload(self):
        raw = {
            "category": "backpack",
            "primary_color": "black",
            "secondary_colors": ["red", "silver"],
            "brand": "Nike",
            "model": "Air Max",
            "visible_text": ["Nike", "Air"],
            "distinctive_features": ["Red zipper", "Nike swoosh logo"],
            "condition": "good",
            "confidence": 0.94,
        }
        normalized = normalize_ai_vision_output(raw)
        self.assertEqual(normalized["category"], "backpack")
        self.assertEqual(normalized["primary_color"], "black")
        self.assertEqual(normalized["secondary_colors"], ["red", "silver"])
        self.assertEqual(normalized["brand"], "Nike")
        self.assertEqual(normalized["model"], "Air Max")
        self.assertEqual(normalized["visible_text"], ["Nike", "Air"])
        self.assertEqual(len(normalized["distinctive_features"]), 2)
        self.assertEqual(normalized["condition"], "good")
        self.assertEqual(normalized["confidence"], 0.94)

    def test_normalize_partial_and_missing_payload(self):
        raw = {
            "category": "Smartphone",
            "primary_color": "BLUE",
            "brand": "null",
            "condition": "invalid_condition_value",
            "confidence": "not_a_number",
        }
        normalized = normalize_ai_vision_output(raw)
        self.assertEqual(normalized["category"], "smartphone")
        self.assertEqual(normalized["primary_color"], "blue")
        self.assertIsNone(normalized["brand"])
        self.assertEqual(normalized["secondary_colors"], [])
        self.assertEqual(normalized["condition"], "unknown")
        self.assertEqual(normalized["confidence"], 0.85)


class TestVisionAnalysisExecution(unittest.TestCase):
    """Test analyze_item_image function across providers and error states."""

    def test_analyze_with_mock_provider(self):
        with patch.dict(os.environ, {"AI_PROVIDER": "mock", "AI_API_KEY": "test"}, clear=True):
            res = analyze_item_image(SAMPLE_PNG_BYTES)
            self.assertTrue(res["success"])
            self.assertIsNotNone(res["data"])
            self.assertEqual(res["data"]["category"], "backpack")
            self.assertEqual(res["data"]["brand"], "Nike")

    def test_analyze_with_gemini_mocked_rest_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps(
                                    {
                                        "category": "water bottle",
                                        "primary_color": "blue",
                                        "secondary_colors": ["black"],
                                        "brand": "Hydro Flask",
                                        "model": None,
                                        "visible_text": ["Hydro Flask"],
                                        "distinctive_features": ["Dent on bottom edge"],
                                        "condition": "used",
                                        "confidence": 0.91,
                                    }
                                )
                            }
                        ]
                    }
                }
            ]
        }

        with patch.dict(os.environ, {"AI_PROVIDER": "google", "AI_API_KEY": "valid_key"}, clear=True):
            with patch("requests.post", return_value=mock_response):
                res = analyze_item_image(SAMPLE_PNG_BYTES)
                self.assertTrue(res["success"])
                self.assertEqual(res["data"]["category"], "water bottle")
                self.assertEqual(res["data"]["brand"], "Hydro Flask")
                self.assertEqual(res["data"]["condition"], "used")

    def test_analyze_with_gemini_api_rate_limit(self):
        mock_response = MagicMock()
        mock_response.status_code = 429

        with patch.dict(os.environ, {"AI_PROVIDER": "google", "AI_API_KEY": "valid_key"}, clear=True):
            with patch("requests.post", return_value=mock_response):
                res = analyze_item_image(SAMPLE_PNG_BYTES)
                self.assertFalse(res["success"])
                self.assertIn("rate limit", res["error"].lower())

    def test_analyze_with_invalid_image_returns_safe_error(self):
        res = analyze_item_image(b"not_an_image_file")
        self.assertFalse(res["success"])
        self.assertIn("valid", res["error"].lower())

    def test_analyze_with_unconfigured_api_key_returns_safe_error(self):
        with patch.dict(os.environ, {"AI_PROVIDER": "google", "AI_API_KEY": "", "GEMINI_API_KEY": ""}, clear=True):
            res = analyze_item_image(SAMPLE_PNG_BYTES)
            self.assertFalse(res["success"])
            self.assertIsNone(res["data"])
            self.assertIn("not configured", res["error"].lower())

    def test_analyze_charger_multimodal_does_not_return_backpack(self):
        charger_mock_response = MagicMock()
        charger_mock_response.status_code = 200
        charger_mock_response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps(
                                    {
                                        "category": "electronics",
                                        "primary_color": "white",
                                        "secondary_colors": [],
                                        "brand": "Apple",
                                        "model": "20W USB-C Power Adapter",
                                        "visible_text": ["20W", "Designed by Apple"],
                                        "distinctive_features": ["USB-C port on bottom"],
                                        "condition": "good",
                                        "confidence": 0.95,
                                    }
                                )
                            }
                        ]
                    }
                }
            ]
        }

        with patch.dict(os.environ, {"AI_PROVIDER": "google", "AI_API_KEY": "valid_key"}, clear=True):
            with patch("requests.post", return_value=charger_mock_response):
                res = analyze_item_image(SAMPLE_PNG_BYTES)
                self.assertTrue(res["success"])
                self.assertEqual(res["data"]["category"], "electronics")
                self.assertEqual(res["data"]["brand"], "Apple")
                self.assertEqual(res["data"]["primary_color"], "white")
                self.assertNotEqual(res["data"]["category"], "backpack")
                self.assertNotEqual(res["data"]["brand"], "Nike")


class TestFlaskAppVisionIntegration(unittest.TestCase):
    """Test Flask routes integrating AI image analysis and reporting."""

    @classmethod
    def setUpClass(cls):
        os.environ["DATABASE_URL"] = "sqlite:///:memory:"
        os.environ["SECRET_KEY"] = "test-secret-key-12345678901234567890"
        os.environ["AI_PROVIDER"] = "mock"
        os.environ["AI_API_KEY"] = "test"

        # Import app
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

    def test_analyze_image_endpoint_authenticated(self):
        with self.client.session_transaction() as sess:
            sess["user_email"] = "student@ced.alliance.edu.in"

        b64 = base64.b64encode(SAMPLE_PNG_BYTES).decode("utf-8")
        resp = self.client.post(
            "/api/ai/analyze-image",
            json={"image": f"data:image/png;base64,{b64}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertIn("category", data["data"])

    def test_report_item_persists_ai_metadata(self):
        with self.client.session_transaction() as sess:
            sess["user_email"] = "student@ced.alliance.edu.in"

        ai_payload = {
            "category": "backpack",
            "primary_color": "black",
            "secondary_colors": ["red"],
            "brand": "Nike",
            "model": "Air",
            "visible_text": ["Nike"],
            "distinctive_features": ["red zipper"],
            "condition": "good",
            "confidence": 0.95,
        }

        resp = self.client.post(
            "/api/report",
            data={
                "name": "Black Nike Backpack",
                "category": "Accessories",
                "location": "Library 2nd Floor",
                "secret_detail": "Contains calculus notebook",
                "ai_metadata": json.dumps(ai_payload),
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["ai_status"], "completed")

        # Verify in database
        with self.app.app_context():
            item = self.app_module.db.session.get(self.app_module.Item, data["item_id"])
            self.assertIsNotNone(item)
            self.assertEqual(item.name, "Black Nike Backpack")
            self.assertEqual(item.ai_category, "backpack")
            self.assertEqual(item.ai_primary_color, "black")
            self.assertEqual(item.ai_brand, "Nike")
            self.assertEqual(item.ai_condition, "good")
            self.assertEqual(item.ai_confidence, 0.95)
            self.assertEqual(item.ai_analysis_status, "completed")


if __name__ == "__main__":
    unittest.main()
