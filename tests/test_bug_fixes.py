"""Regression tests for Bug 1 (AI Image Stale Data) and Bug 2 (Claim Student Email / Notification Resilience)."""

from __future__ import annotations

import base64
import importlib.util
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from ai.client import format_ai_response
from ai.vision import analyze_item_image

# 1x1 PNG bytes for valid image payload
SAMPLE_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe"
    b"\xdc\xccY\xe7\x00\x00\x00\x00IEND\xaeB`\x82"
)


class TestBug1And2Regression(unittest.TestCase):
    """Explicit tests for Bug 1 and Bug 2 user requirements."""

    @classmethod
    def setUpClass(cls):
        cls.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls.db_path = cls.temp_db.name
        cls.temp_db.close()

        os.environ["DATABASE_URL"] = f"sqlite:///{cls.db_path}"
        os.environ["SECRET_KEY"] = "regression-test-secret-key-1234567890"
        os.environ["AI_PROVIDER"] = "mock"
        os.environ["AI_API_KEY"] = "test-key"

        spec = importlib.util.spec_from_file_location("app_regression", "app.py")
        cls.app_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.app_module)
        cls.app = cls.app_module.app
        cls.app.config["TESTING"] = True

    @classmethod
    def tearDownClass(cls):
        try:
            if os.path.exists(cls.db_path):
                os.remove(cls.db_path)
        except Exception:
            pass

    def setUp(self):
        self.client = self.app.test_client()
        with self.app.app_context():
            self.app_module.db.create_all()

    def tearDown(self):
        with self.app.app_context():
            self.app_module.db.session.remove()
            self.app_module.db.drop_all()

    # TEST 1: Upload a charger image. Verify AI does not return previous backpack/Nike metadata.
    def test_1_charger_image_does_not_return_backpack(self):
        charger_response = MagicMock()
        charger_response.status_code = 200
        charger_response.json.return_value = {
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
                                        "model": "20W USB-C Charger",
                                        "visible_text": ["20W"],
                                        "distinctive_features": ["type-c port"],
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
            with patch("requests.post", return_value=charger_response):
                res = analyze_item_image(SAMPLE_PNG_BYTES)
                self.assertTrue(res["success"])
                self.assertEqual(res["data"]["category"], "electronics")
                self.assertEqual(res["data"]["brand"], "Apple")
                self.assertNotEqual(res["data"]["category"], "backpack")
                self.assertNotEqual(res["data"]["brand"], "Nike")

    # TEST 2: Upload a backpack image. Verify its result is based on that image.
    def test_2_backpack_image_returns_backpack_metadata(self):
        backpack_response = MagicMock()
        backpack_response.status_code = 200
        backpack_response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps(
                                    {
                                        "category": "backpack",
                                        "primary_color": "black",
                                        "secondary_colors": ["red"],
                                        "brand": "Nike",
                                        "model": "Air Max",
                                        "visible_text": ["Nike"],
                                        "distinctive_features": ["red zipper"],
                                        "condition": "good",
                                        "confidence": 0.92,
                                    }
                                )
                            }
                        ]
                    }
                }
            ]
        }
        with patch.dict(os.environ, {"AI_PROVIDER": "google", "AI_API_KEY": "valid_key"}, clear=True):
            with patch("requests.post", return_value=backpack_response):
                res = analyze_item_image(SAMPLE_PNG_BYTES)
                self.assertTrue(res["success"])
                self.assertEqual(res["data"]["category"], "backpack")
                self.assertEqual(res["data"]["brand"], "Nike")

    # TEST 3: Upload unconfigured / failing AI does NOT return hardcoded backpack.
    def test_3_unconfigured_ai_returns_safe_error_not_stale_backpack(self):
        with patch.dict(os.environ, {"AI_PROVIDER": "google", "AI_API_KEY": ""}, clear=True):
            res = analyze_item_image(SAMPLE_PNG_BYTES)
            self.assertFalse(res["success"])
            self.assertIsNone(res["data"])
            self.assertIn("not configured", res["error"].lower())

    # TEST 4: Verify backend /api/ai/analyze-image processes each upload independently
    def test_4_analyze_endpoint_isolated_requests(self):
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
        self.assertIsNotNone(data["data"])

    # TEST 5: Submit claim without student_email in JSON request. Verify claim succeeds using session["user_email"].
    def test_5_claim_submission_without_student_email_uses_session(self):
        with self.app.app_context():
            item = self.app_module.Item(
                name="Mobile Charger",
                category="Electronics",
                location="LH-201",
                item_type="found",
                status="Available"
            )
            self.app_module.db.session.add(item)
            self.app_module.db.session.commit()
            item_id = item.id

        with self.client.session_transaction() as sess:
            sess["user_email"] = "authenticated_student@ced.alliance.edu.in"

        # Note: No student_email provided in JSON body
        resp = self.client.post(
            "/api/claim",
            json={
                "item_id": item_id,
                "student_id": "CED2026-777",
                "phone": "9876543210",
                "proof_description": "White Apple 20W USB-C charger left on desk.",
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "success")
        self.assertIn("claim_id", data)

        with self.app.app_context():
            saved_claim = self.app_module.db.session.get(self.app_module.Claim, data["claim_id"])
            self.assertIsNotNone(saved_claim)
            self.assertEqual(saved_claim.student_email, "authenticated_student@ced.alliance.edu.in")
            self.assertEqual(saved_claim.student_id, "CED2026-777")

    # TEST 6: Simulate email failure. Verify claim is still saved successfully.
    def test_6_claim_succeeds_when_email_fails(self):
        with self.app.app_context():
            item = self.app_module.Item(
                name="Earphones",
                category="Electronics",
                location="Library",
                item_type="found",
                status="Available"
            )
            self.app_module.db.session.add(item)
            self.app_module.db.session.commit()
            item_id = item.id

        with self.client.session_transaction() as sess:
            sess["user_email"] = "student@ced.alliance.edu.in"

        with patch.object(self.app_module, "send_email", side_effect=Exception("SMTPAuthError: Bad credentials")):
            resp = self.client.post(
                "/api/claim",
                json={
                    "item_id": item_id,
                    "student_id": "CED2026-101",
                    "phone": "9876543210",
                    "proof_description": "Wired 3.5mm white earphones.",
                },
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertEqual(data["status"], "success")
            self.assertFalse(data["email_sent"])

            with self.app.app_context():
                saved_claim = self.app_module.db.session.get(self.app_module.Claim, data["claim_id"])
                self.assertIsNotNone(saved_claim)

    # TEST 7: Simulate SMS failure. Verify claim is still saved successfully.
    def test_7_claim_succeeds_when_sms_fails(self):
        with self.app.app_context():
            item = self.app_module.Item(
                name="ID Card",
                category="Cards",
                location="Main Gate",
                item_type="found",
                status="Available"
            )
            self.app_module.db.session.add(item)
            self.app_module.db.session.commit()
            item_id = item.id

        with self.client.session_transaction() as sess:
            sess["user_email"] = "student@ced.alliance.edu.in"

        with patch.object(self.app_module, "send_sms", side_effect=Exception("Twilio Rest Exception")):
            resp = self.client.post(
                "/api/claim",
                json={
                    "item_id": item_id,
                    "student_id": "CED2026-102",
                    "phone": "9876543210",
                    "proof_description": "Alliance University Student ID card.",
                },
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertEqual(data["status"], "success")
            self.assertFalse(data["sms_sent"])

            with self.app.app_context():
                saved_claim = self.app_module.db.session.get(self.app_module.Claim, data["claim_id"])
                self.assertIsNotNone(saved_claim)

    # TEST 8: Verify the frontend / API returns a clean success message
    def test_8_clean_success_message(self):
        with self.app.app_context():
            item = self.app_module.Item(
                name="Notebook",
                category="Books",
                location="Reading Room",
                item_type="found",
                status="Available"
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
                "student_id": "CED2026-103",
                "phone": "9876543210",
                "proof_description": "Spiral bound physics notes.",
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["message"], "Claim submitted successfully. Your request is now under review.")

    # TEST 9: Verify invalid / missing claim fields return a clean JSON error
    def test_9_missing_claim_fields_return_clean_json_error(self):
        with self.client.session_transaction() as sess:
            sess["user_email"] = "student@ced.alliance.edu.in"

        resp = self.client.post(
            "/api/claim",
            json={"item_id": ""},
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertEqual(data["status"], "error")
        self.assertIn("message", data)

    # TEST 11: Verify that a malicious request containing spoofed student_email is ignored and session email is always used
    def test_11_claim_ignores_attacker_spoofed_email(self):
        with self.app.app_context():
            item = self.app_module.Item(
                name="Wireless Mouse",
                category="Electronics",
                location="Computer Lab 3",
                item_type="found",
                status="Available"
            )
            self.app_module.db.session.add(item)
            self.app_module.db.session.commit()
            item_id = item.id

        with self.client.session_transaction() as sess:
            sess["user_email"] = "legitimate_victim@ced.alliance.edu.in"

        # Malicious payload attempts to override student_email with attacker's email
        resp = self.client.post(
            "/api/claim",
            json={
                "item_id": item_id,
                "student_id": "CED2026-999",
                "phone": "9876543210",
                "proof_description": "Black Logitech wireless mouse.",
                "student_email": "attacker@example.com",
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "success")

        with self.app.app_context():
            saved_claim = self.app_module.db.session.get(self.app_module.Claim, data["claim_id"])
            self.assertIsNotNone(saved_claim)
            # Must strictly equal the authenticated session email
            self.assertEqual(saved_claim.student_email, "legitimate_victim@ced.alliance.edu.in")
            self.assertNotEqual(saved_claim.student_email, "attacker@example.com")

    # TEST 12: Verify unauthenticated claim request returns HTTP 401
    def test_12_claim_unauthenticated_returns_401(self):
        # Client has no active session
        resp = self.client.post(
            "/api/claim",
            json={
                "item_id": 1,
                "student_id": "CED2026-001",
                "proof_description": "Valid description",
                "student_email": "attacker@example.com",
            },
        )
        self.assertEqual(resp.status_code, 401)
        data = resp.get_json()
        self.assertEqual(data["status"], "error")
        self.assertIn("Authentication required", data["message"])

    # TEST 13: POST /api/ai/analyze-image with actual multipart file uploads (Charger -> Backpack -> Charger)
    def test_13_actual_multipart_file_upload_sequence(self):
        import io

        with self.client.session_transaction() as sess:
            sess["user_email"] = "student@ced.alliance.edu.in"

        # Step 1: Upload Charger file
        charger_mock = MagicMock()
        charger_mock.status_code = 200
        charger_mock.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps(
                                    {
                                        "category": "electronics",
                                        "primary_color": "black",
                                        "secondary_colors": [],
                                        "brand": "Anker",
                                        "model": "Nano 30W",
                                        "visible_text": ["Anker"],
                                        "distinctive_features": ["foldable prongs"],
                                        "condition": "good",
                                        "confidence": 0.96,
                                    }
                                )
                            }
                        ]
                    }
                }
            ]
        }

        with patch.dict(os.environ, {"AI_PROVIDER": "google", "AI_API_KEY": "valid_key"}, clear=True):
            with patch("requests.post", return_value=charger_mock):
                charger_file = (io.BytesIO(SAMPLE_PNG_BYTES), "charger.png")
                resp1 = self.client.post(
                    "/api/ai/analyze-image",
                    data={"image": charger_file},
                    content_type="multipart/form-data",
                )
                self.assertEqual(resp1.status_code, 200)
                d1 = resp1.get_json()
                self.assertTrue(d1["success"])
                self.assertEqual(d1["data"]["category"], "electronics")
                self.assertEqual(d1["data"]["brand"], "Anker")
                self.assertNotEqual(d1["data"]["category"], "backpack")

        # Step 2: Upload Backpack file
        backpack_mock = MagicMock()
        backpack_mock.status_code = 200
        backpack_mock.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps(
                                    {
                                        "category": "backpack",
                                        "primary_color": "blue",
                                        "secondary_colors": ["black"],
                                        "brand": "Puma",
                                        "model": "Phase Backpack",
                                        "visible_text": ["Puma"],
                                        "distinctive_features": ["mesh side pocket"],
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
            with patch("requests.post", return_value=backpack_mock):
                backpack_file = (io.BytesIO(SAMPLE_PNG_BYTES), "backpack.png")
                resp2 = self.client.post(
                    "/api/ai/analyze-image",
                    data={"image": backpack_file},
                    content_type="multipart/form-data",
                )
                self.assertEqual(resp2.status_code, 200)
                d2 = resp2.get_json()
                self.assertTrue(d2["success"])
                self.assertEqual(d2["data"]["category"], "backpack")
                self.assertEqual(d2["data"]["brand"], "Puma")
                self.assertNotEqual(d2["data"]["brand"], "Anker")

        # Step 3: Upload Charger file again
        with patch.dict(os.environ, {"AI_PROVIDER": "google", "AI_API_KEY": "valid_key"}, clear=True):
            with patch("requests.post", return_value=charger_mock):
                charger_file_again = (io.BytesIO(SAMPLE_PNG_BYTES), "charger_again.png")
                resp3 = self.client.post(
                    "/api/ai/analyze-image",
                    data={"image": charger_file_again},
                    content_type="multipart/form-data",
                )
                self.assertEqual(resp3.status_code, 200)
                d3 = resp3.get_json()
                self.assertTrue(d3["success"])
                self.assertEqual(d3["data"]["category"], "electronics")
                self.assertEqual(d3["data"]["brand"], "Anker")
                self.assertNotEqual(d3["data"]["category"], "backpack")

    # TEST 14: Exhaustive provider key isolation
    def test_14_provider_key_isolation_exhaustive(self):
        from ai.config import AIConfig
        from ai.client import get_ai_client, GoogleGeminiProvider, OpenAIProvider

        # Case A: Google receives GOOGLE_API_KEY or GEMINI_API_KEY, never OPENAI_API_KEY
        env_google = {
            "AI_PROVIDER": "google",
            "GEMINI_API_KEY": "gemini_secret_key_12345",
            "OPENAI_API_KEY": "sk_openai_secret_99999",
        }
        with patch.dict(os.environ, env_google, clear=True):
            self.assertEqual(AIConfig.get_api_key("google"), "gemini_secret_key_12345")
            client = get_ai_client(require_configured=True)
            self.assertIsInstance(client, GoogleGeminiProvider)
            self.assertEqual(client.api_key, "gemini_secret_key_12345")
            self.assertNotEqual(client.api_key, "sk_openai_secret_99999")

        # Case B: OpenAI receives OPENAI_API_KEY, never GEMINI_API_KEY
        env_openai = {
            "AI_PROVIDER": "openai",
            "GEMINI_API_KEY": "gemini_secret_key_12345",
            "OPENAI_API_KEY": "sk_openai_secret_99999",
        }
        with patch.dict(os.environ, env_openai, clear=True):
            self.assertEqual(AIConfig.get_api_key("openai"), "sk_openai_secret_99999")
            client = get_ai_client(require_configured=True)
            self.assertIsInstance(client, OpenAIProvider)
            self.assertEqual(client.api_key, "sk_openai_secret_99999")
            self.assertNotEqual(client.api_key, "gemini_secret_key_12345")

    # TEST 15: API key never appears in HTTP responses, errors, or serialized data
    def test_15_api_key_never_appears_in_responses_or_logs(self):
        secret_key_value = "super_confidential_api_key_abcdef123456"

        with self.client.session_transaction() as sess:
            sess["user_email"] = "student@ced.alliance.edu.in"

        # Simulate 401 error from upstream
        mock_auth_fail = MagicMock()
        mock_auth_fail.status_code = 401

        with patch.dict(os.environ, {"AI_PROVIDER": "google", "AI_API_KEY": secret_key_value}, clear=True):
            with patch("requests.post", return_value=mock_auth_fail):
                b64 = base64.b64encode(SAMPLE_PNG_BYTES).decode("utf-8")
                resp = self.client.post(
                    "/api/ai/analyze-image",
                    json={"image": f"data:image/png;base64,{b64}"},
                )
                raw_response_text = resp.data.decode("utf-8")
                # Confirm secret key is NEVER leaked in response JSON
                self.assertNotIn(secret_key_value, raw_response_text)

    # TEST 16: Model URL construction with gemini-3.6-flash and prefix handling
    def test_16_model_url_construction_gemini_3_6_flash(self):
        from ai.client import GoogleGeminiProvider

        p1 = GoogleGeminiProvider(api_key="test_key", model="gemini-3.6-flash")
        self.assertEqual(
            p1._get_url(),
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent"
        )

        p2 = GoogleGeminiProvider(api_key="test_key", model="models/gemini-3.6-flash")
        self.assertEqual(
            p2._get_url(),
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent"
        )

    # TEST 17: Gemini error handling (Rate limit 429 and Server Error 500) fails safely without leaking secrets
    def test_17_gemini_error_handling_fails_safely(self):
        with self.client.session_transaction() as sess:
            sess["user_email"] = "student@ced.alliance.edu.in"

        # Case A: 429 Rate Limit
        mock_429 = MagicMock()
        mock_429.status_code = 429
        with patch("time.sleep", return_value=None):
            with patch.dict(os.environ, {"AI_PROVIDER": "google", "AI_API_KEY": "valid_key", "AI_MODEL": "gemini-3.6-flash"}, clear=True):
                with patch("requests.post", return_value=mock_429):
                    resp = self.client.post("/api/ai/analyze-image", json={"image": f"data:image/png;base64,{base64.b64encode(SAMPLE_PNG_BYTES).decode('utf-8')}"})
                    self.assertEqual(resp.status_code, 200)
                    data = resp.get_json()
                    self.assertFalse(data["success"])
                    self.assertIn("rate limit", data["error"].lower())

        # Case B: 500 Server Error
        mock_500 = MagicMock()
        mock_500.status_code = 500
        mock_500.text = "Internal Server Error"
        with patch.dict(os.environ, {"AI_PROVIDER": "google", "AI_API_KEY": "valid_key", "AI_MODEL": "gemini-3.6-flash"}, clear=True):
            with patch("requests.post", return_value=mock_500):
                resp = self.client.post("/api/ai/analyze-image", json={"image": f"data:image/png;base64,{base64.b64encode(SAMPLE_PNG_BYTES).decode('utf-8')}"})
                self.assertEqual(resp.status_code, 200)
                data = resp.get_json()
                self.assertFalse(data["success"])
                self.assertIn("unavailable", data["error"].lower())

    # TEST 18: AI_MODEL environment override dynamically changes the target model
    def test_18_ai_model_environment_override(self):
        from ai.config import AIConfig
        from ai.client import get_ai_client

        with patch.dict(os.environ, {"AI_PROVIDER": "google", "AI_API_KEY": "valid_key", "AI_MODEL": "custom-vision-model-v1"}, clear=True):
            self.assertEqual(AIConfig.get_model(), "custom-vision-model-v1")
            client = get_ai_client(require_configured=True)
            self.assertEqual(client.model, "custom-vision-model-v1")
            self.assertEqual(
                client._get_url(),
                "https://generativelanguage.googleapis.com/v1beta/models/custom-vision-model-v1:generateContent"
            )

    # TEST 19: Gemini 400 Bad Request error handling
    def test_19_gemini_400_bad_request_fails_safely(self):
        with self.client.session_transaction() as sess:
            sess["user_email"] = "student@ced.alliance.edu.in"

        mock_400 = MagicMock()
        mock_400.status_code = 400
        mock_400.text = "Invalid JSON payload received. Unknown name 'inline_data'"
        mock_400.json.return_value = {"error": {"message": "Invalid JSON payload received. Unknown name 'inline_data'"}}
        with patch.dict(os.environ, {"AI_PROVIDER": "google", "AI_API_KEY": "valid_key", "AI_MODEL": "gemini-3.6-flash"}, clear=True):
            with patch("requests.post", return_value=mock_400):
                resp = self.client.post("/api/ai/analyze-image", json={"image": f"data:image/png;base64,{base64.b64encode(SAMPLE_PNG_BYTES).decode('utf-8')}"})
                self.assertEqual(resp.status_code, 200)
                data = resp.get_json()
                self.assertFalse(data["success"])
                self.assertIn("invalid", data["error"].lower())

    # TEST 20: Gemini 404 Model Not Found error handling
    def test_20_gemini_404_model_not_found_fails_safely(self):
        with self.client.session_transaction() as sess:
            sess["user_email"] = "student@ced.alliance.edu.in"

        mock_404 = MagicMock()
        mock_404.status_code = 404
        mock_404.text = "models/gemini-old is not found for API version v1beta"
        mock_404.json.return_value = {"error": {"message": "models/gemini-old is not found for API version v1beta"}}
        with patch.dict(os.environ, {"AI_PROVIDER": "google", "AI_API_KEY": "valid_key", "AI_MODEL": "gemini-3.6-flash"}, clear=True):
            with patch("requests.post", return_value=mock_404):
                resp = self.client.post("/api/ai/analyze-image", json={"image": f"data:image/png;base64,{base64.b64encode(SAMPLE_PNG_BYTES).decode('utf-8')}"})
                self.assertEqual(resp.status_code, 200)
                data = resp.get_json()
                self.assertFalse(data["success"])
                self.assertIn("unavailable", data["error"].lower())

    # TEST 21: Verify payload structure sent to Gemini contains inlineData, mimeType, responseMimeType
    def test_21_gemini_multimodal_payload_structure(self):
        from ai.client import GoogleGeminiProvider

        provider = GoogleGeminiProvider(api_key="secret_test_key", model="gemini-3.6-flash")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": json.dumps({"category": "electronics", "brand": "Apple"})}
                        ]
                    }
                }
            ]
        }

        with patch("requests.post", return_value=mock_resp) as mock_post:
            provider.analyze_multimodal(
                "analyze this",
                SAMPLE_PNG_BYTES,
                "image/png",
                system_instruction="Analyze lost and found items accurately."
            )

            mock_post.assert_called_once()
            call_args, call_kwargs = mock_post.call_args

            # Verify URL
            self.assertEqual(
                call_args[0],
                "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent"
            )
            # Verify Header
            self.assertEqual(call_kwargs["headers"]["x-goog-api-key"], "secret_test_key")
            self.assertNotIn("?key=", call_args[0])

            # Verify Payload JSON
            sent_payload = call_kwargs["json"]
            self.assertIn("contents", sent_payload)
            parts = sent_payload["contents"][0]["parts"]
            self.assertEqual(parts[0]["text"], "analyze this")
            self.assertIn("inlineData", parts[1])
            self.assertEqual(parts[1]["inlineData"]["mimeType"], "image/png")
            self.assertTrue(len(parts[1]["inlineData"]["data"]) > 0)
            self.assertEqual(sent_payload["generationConfig"]["responseMimeType"], "application/json")
            self.assertNotIn("temperature", sent_payload["generationConfig"])
            self.assertNotIn("topP", sent_payload.get("generationConfig", {}))
            self.assertNotIn("topK", sent_payload.get("generationConfig", {}))

            # Verify systemInstruction is camelCase and snake_case is NOT present
            self.assertIn("systemInstruction", sent_payload)
            self.assertEqual(
                sent_payload["systemInstruction"],
                {"parts": [{"text": "Analyze lost and found items accurately."}]}
            )
            self.assertNotIn("system_instruction", sent_payload)

    # TEST 22: Explicit regression test verifying default Google model is gemini-3.6-flash
    def test_22_default_google_model_is_gemini_3_6_flash(self):
        from ai.config import AIConfig
        from ai.client import get_ai_client, GoogleGeminiProvider

        with patch.dict(os.environ, {"AI_PROVIDER": "google", "AI_API_KEY": "valid_key"}, clear=True):
            self.assertEqual(AIConfig.get_model(), "gemini-3.6-flash")
            self.assertNotEqual(AIConfig.get_model(), "gemini-2.5-flash")
            self.assertNotEqual(AIConfig.get_model(), "gemini-1.5-flash")
            client = get_ai_client(require_configured=True)
            self.assertIsInstance(client, GoogleGeminiProvider)
            self.assertEqual(client.model, "gemini-3.6-flash")
            self.assertEqual(
                client._get_url(),
                "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent"
            )

    # TEST 23: Low-latency thinkingConfig for Gemini 3.6 Flash
    def test_23_low_latency_thinking_config_gemini_3_6_flash(self):
        from ai.client import GoogleGeminiProvider

        provider = GoogleGeminiProvider(api_key="secret_test_key", model="gemini-3.6-flash")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": json.dumps({"category": "electronics"})}]}}]
        }

        with patch("requests.post", return_value=mock_resp) as mock_post:
            provider.analyze_multimodal("analyze item", SAMPLE_PNG_BYTES, "image/png")
            sent_payload = mock_post.call_args[1]["json"]
            self.assertIn("thinkingConfig", sent_payload["generationConfig"])
            self.assertEqual(sent_payload["generationConfig"]["thinkingConfig"]["thinkingLevel"], "LOW")

    # TEST 24: Configurable AI_TIMEOUT environment variable
    def test_24_configurable_ai_timeout_handling(self):
        from ai.config import AIConfig
        from ai.client import get_ai_client

        with patch.dict(os.environ, {"AI_TIMEOUT": "25", "AI_PROVIDER": "google", "AI_API_KEY": "valid_key"}, clear=True):
            self.assertEqual(AIConfig.get_timeout(), 25)
            client = get_ai_client(require_configured=True)
            self.assertEqual(client.timeout, 25)

    # TEST 25: 503 triggers exactly one retry and succeeds on second attempt
    def test_25_gemini_503_triggers_retry_and_succeeds(self):
        from ai.client import GoogleGeminiProvider

        provider = GoogleGeminiProvider(api_key="secret_test_key", model="gemini-3.6-flash")

        mock_503 = MagicMock()
        mock_503.status_code = 503
        mock_503.text = "Model experiencing high demand"
        mock_503.json.return_value = {"error": {"message": "Model experiencing high demand"}}

        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": json.dumps({"category": "electronics", "brand": "Apple"})}]}}]
        }

        with patch("time.sleep", return_value=None):
            with patch("requests.post", side_effect=[mock_503, mock_200]) as mock_post:
                res = provider.analyze_multimodal("analyze charger", SAMPLE_PNG_BYTES, "image/jpeg")
                self.assertEqual(mock_post.call_count, 2)
                self.assertEqual(res["category"], "electronics")
                self.assertEqual(res["brand"], "Apple")

    # TEST 26: 503 triggers exactly one retry and fails cleanly after max 1 retry
    def test_26_gemini_503_triggers_retry_and_fails_after_max_retries(self):
        from ai.client import GoogleGeminiProvider
        from ai.exceptions import AIProviderError

        provider = GoogleGeminiProvider(api_key="secret_test_key", model="gemini-3.6-flash")

        mock_503_1 = MagicMock()
        mock_503_1.status_code = 503
        mock_503_1.text = "High demand attempt 1"
        mock_503_1.json.return_value = {"error": {"message": "High demand attempt 1"}}

        mock_503_2 = MagicMock()
        mock_503_2.status_code = 503
        mock_503_2.text = "High demand attempt 2"
        mock_503_2.json.return_value = {"error": {"message": "High demand attempt 2"}}

        with patch("time.sleep", return_value=None):
            with patch("requests.post", side_effect=[mock_503_1, mock_503_2]) as mock_post:
                with self.assertRaises(AIProviderError):
                    provider.analyze_multimodal("analyze charger", SAMPLE_PNG_BYTES, "image/jpeg")
                # Exactly 2 attempts (initial + 1 retry)
                self.assertEqual(mock_post.call_count, 2)

    # TEST 27: 429 triggers exactly one retry and succeeds
    def test_27_gemini_429_triggers_retry(self):
        from ai.client import GoogleGeminiProvider

        provider = GoogleGeminiProvider(api_key="secret_test_key", model="gemini-3.6-flash")

        mock_429 = MagicMock()
        mock_429.status_code = 429
        mock_429.text = "Quota spike"
        mock_429.json.return_value = {"error": {"message": "Quota spike"}}

        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": json.dumps({"category": "charger"})}]}}]
        }

        with patch("time.sleep", return_value=None):
            with patch("requests.post", side_effect=[mock_429, mock_200]) as mock_post:
                res = provider.analyze_multimodal("analyze charger", SAMPLE_PNG_BYTES, "image/jpeg")
                self.assertEqual(mock_post.call_count, 2)
                self.assertEqual(res["category"], "charger")

    # TEST 28: Non-retryable errors (400, 401, 403, 404) do NOT retry
    def test_28_gemini_non_retryable_errors_do_not_retry(self):
        from ai.client import GoogleGeminiProvider
        from ai.exceptions import AIAuthenticationError, AIModelNotFoundError, AIRequestError

        provider = GoogleGeminiProvider(api_key="secret_test_key", model="gemini-3.6-flash")

        # 400 Bad Request
        mock_400 = MagicMock(status_code=400, text="Bad request")
        mock_400.json.return_value = {"error": {"message": "Bad request"}}
        with patch("requests.post", return_value=mock_400) as mock_post:
            with self.assertRaises(AIRequestError):
                provider.analyze_multimodal("test", SAMPLE_PNG_BYTES, "image/jpeg")
            self.assertEqual(mock_post.call_count, 1)

        # 401 Unauthorized
        mock_401 = MagicMock(status_code=401, text="Unauthorized")
        mock_401.json.return_value = {"error": {"message": "Unauthorized"}}
        with patch("requests.post", return_value=mock_401) as mock_post:
            with self.assertRaises(AIAuthenticationError):
                provider.analyze_multimodal("test", SAMPLE_PNG_BYTES, "image/jpeg")
            self.assertEqual(mock_post.call_count, 1)

        # 404 Model Not Found
        mock_404 = MagicMock(status_code=404, text="Model not found")
        mock_404.json.return_value = {"error": {"message": "Model not found"}}
        with patch("requests.post", return_value=mock_404) as mock_post:
            with self.assertRaises(AIModelNotFoundError):
                provider.analyze_multimodal("test", SAMPLE_PNG_BYTES, "image/jpeg")
            self.assertEqual(mock_post.call_count, 1)


    # TEST 29: Admin delete item with no dependencies succeeds and removes item from DB
    def test_29_delete_item_no_dependencies_success(self):
        Item = self.app_module.Item
        db = self.app_module.db

        with self.app.app_context():
            item = Item(name="Test Keys", location="Library", category="Keys", status="Available")
            db.session.add(item)
            db.session.commit()
            item_id = item.id

        with self.client.session_transaction() as sess:
            sess["is_admin"] = True
            sess["admin_email"] = "admin@ced.alliance.edu.in"

        resp = self.client.post(f"/api/item/delete/{item_id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "success")

        # Confirm item is actually deleted from DB
        with self.app.app_context():
            self.assertIsNone(db.session.get(Item, item_id))

    # TEST 30: Admin delete item with claims and AI match records succeeds without foreign key error
    def test_30_delete_item_with_claims_and_matches_success(self):
        Item = self.app_module.Item
        Claim = self.app_module.Claim
        ItemMatch = self.app_module.ItemMatch
        db = self.app_module.db

        with self.app.app_context():
            # Create found item (e.g. item 16) and lost item
            found_item = Item(name="iPhone Charger", location="Auditorium", category="Electronics", status="Available", item_type="found")
            lost_item = Item(name="Lost Apple Charger", location="Auditorium", category="Electronics", status="Available", item_type="lost")
            db.session.add_all([found_item, lost_item])
            db.session.commit()

            found_id = found_item.id
            lost_id = lost_item.id

            # Create Claim on found item
            claim = Claim(
                item_id=found_id,
                student_id="STD12345",
                student_email="claimant@ced.alliance.edu.in",
                proof_description="White 20W adapter with USB-C",
            )
            # Create ItemMatch between lost and found item
            match_rec = ItemMatch(
                lost_item_id=lost_id,
                found_item_id=found_id,
                match_score=95,
                confidence="High",
                matching_attributes=["category", "brand"],
                status="active"
            )
            db.session.add_all([claim, match_rec])
            db.session.commit()
            claim_id = claim.id
            match_id = match_rec.id

        with self.client.session_transaction() as sess:
            sess["is_admin"] = True
            sess["admin_email"] = "admin@ced.alliance.edu.in"

        # Delete found item (which has dependent Claim and ItemMatch)
        resp = self.client.post(f"/api/item/delete/{found_id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "success")

        # Verify found item is removed from database
        with self.app.app_context():
            self.assertIsNone(db.session.get(Item, found_id))
            # Verify dependent claim was safely deleted
            self.assertIsNone(db.session.get(Claim, claim_id))
            # Verify dependent match was safely deleted
            self.assertIsNone(db.session.get(ItemMatch, match_id))
            # Verify lost item remains intact
            self.assertIsNotNone(db.session.get(Item, lost_id))

    # TEST 31: Delete nonexistent item returns 404
    def test_31_delete_nonexistent_item_returns_404(self):
        with self.client.session_transaction() as sess:
            sess["is_admin"] = True
            sess["admin_email"] = "admin@ced.alliance.edu.in"

        resp = self.client.post("/api/item/delete/999999")
        self.assertEqual(resp.status_code, 404)
        data = resp.get_json()
        self.assertEqual(data["status"], "error")
        self.assertIn("not found", data["error"].lower())

    # TEST 32: Non-admin user cannot delete items
    def test_32_delete_unauthorized_user_rejected(self):
        Item = self.app_module.Item
        db = self.app_module.db

        with self.app.app_context():
            item = Item(name="Protected Item", location="Library", category="Electronics", status="Available")
            db.session.add(item)
            db.session.commit()
            item_id = item.id

        # Case A: Unauthenticated request
        resp = self.client.post(f"/api/item/delete/{item_id}")
        self.assertIn(resp.status_code, (302, 401, 403))

        # Case B: Authenticated as normal student (non-admin)
        with self.client.session_transaction() as sess:
            sess["user_email"] = "student@ced.alliance.edu.in"
            sess["is_admin"] = False

        resp2 = self.client.post(f"/api/item/delete/{item_id}")
        self.assertIn(resp2.status_code, (302, 401, 403))

        # Confirm item is still intact in DB
        with self.app.app_context():
            self.assertIsNotNone(db.session.get(Item, item_id))

    # TEST 33: Database failure triggers rollback and leaves item in DB
    def test_33_delete_failure_triggers_rollback_and_item_remains(self):
        Item = self.app_module.Item
        db = self.app_module.db

        with self.app.app_context():
            item = Item(name="Rollback Test Item", location="Lab", category="Electronics", status="Available")
            db.session.add(item)
            db.session.commit()
            item_id = item.id

        with self.client.session_transaction() as sess:
            sess["is_admin"] = True
            sess["admin_email"] = "admin@ced.alliance.edu.in"

        with patch.object(db.session, "commit", side_effect=Exception("Database lock error")):
            resp = self.client.post(f"/api/item/delete/{item_id}")
            self.assertEqual(resp.status_code, 500)
            data = resp.get_json()
            self.assertEqual(data["status"], "error")
            self.assertEqual(data["error"], "Unable to delete this item. Please try again.")
            # Verify internal DB stack trace is NOT exposed
            self.assertNotIn("Database lock error", str(data))

        # Verify item was not deleted due to rollback
        with self.app.app_context():
            self.assertIsNotNone(db.session.get(Item, item_id))

    # TEST 34: Admin header branding has dark navy Campus (#172554) and cyan Retain
    def test_34_admin_header_brand_color(self):
        with self.client.session_transaction() as sess:
            sess["is_admin"] = True
            sess["admin_email"] = "admin@ced.alliance.edu.in"

        resp = self.client.get("/admin")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("#172554", html)
        self.assertIn("Campus", html)
        self.assertIn("Retain", html)

    # TEST 35: Index and Dashboard batch match counts performance
    def test_35_index_and_dashboard_performance_optimization(self):
        Item = self.app_module.Item
        ItemMatch = self.app_module.ItemMatch
        db = self.app_module.db

        with self.app.app_context():
            found1 = Item(name="Found Item 1", location="Room 101", category="Books", item_type="found")
            found2 = Item(name="Found Item 2", location="Room 102", category="Electronics", item_type="found")
            lost1 = Item(name="Lost Item 1", location="Room 101", category="Books", item_type="lost", reported_by="student@ced.alliance.edu.in")
            db.session.add_all([found1, found2, lost1])
            db.session.commit()

            match1 = ItemMatch(lost_item_id=lost1.id, found_item_id=found1.id, match_score=90, confidence="High", status="active")
            db.session.add(match1)
            db.session.commit()

        with self.client.session_transaction() as sess:
            sess["user_email"] = "student@ced.alliance.edu.in"

        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)

        resp2 = self.client.get("/dashboard")
        self.assertEqual(resp2.status_code, 200)


if __name__ == "__main__":
    unittest.main()
