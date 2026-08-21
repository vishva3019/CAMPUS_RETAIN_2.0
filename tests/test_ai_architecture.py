"""Tests for AI Architecture foundation."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from ai import (
    AIAuthenticationError,
    AIConfig,
    AIConfigurationError,
    AIError,
    AIInvalidResponseError,
    AIProviderError,
    AIRateLimitError,
    AITimeoutError,
    BaseAIProvider,
    GoogleGeminiProvider,
    MockAIProvider,
    OpenAIProvider,
    analyze_claim,
    analyze_item_image,
    find_potential_matches,
    format_ai_response,
    get_ai_client,
    semantic_search,
)


class TestAIConfig(unittest.TestCase):
    """Test AI configuration loading, validation, and secret masking."""

    def test_default_configuration_when_unset(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(AIConfig.get_provider(), "google")
            self.assertEqual(AIConfig.get_api_key(), "")
            self.assertEqual(AIConfig.get_model(), "gemini-3.6-flash")
            self.assertNotEqual(AIConfig.get_model(), "gemini-2.5-flash")
            self.assertNotEqual(AIConfig.get_model(), "gemini-1.5-flash")
            self.assertFalse(AIConfig.is_configured())
            self.assertEqual(AIConfig.get_masked_api_key(), "NOT_CONFIGURED")

    def test_custom_environment_variables(self):
        custom_env = {
            "AI_PROVIDER": "openai",
            "AI_API_KEY": "sk-proj-testkey123456789",
            "AI_MODEL": "gpt-4o-mini",
            "AI_TIMEOUT": "20",
        }
        with patch.dict(os.environ, custom_env, clear=True):
            self.assertEqual(AIConfig.get_provider(), "openai")
            self.assertEqual(AIConfig.get_api_key(), "sk-proj-testkey123456789")
            self.assertEqual(AIConfig.get_model(), "gpt-4o-mini")
            self.assertEqual(AIConfig.get_timeout(), 20)
            self.assertTrue(AIConfig.is_configured())
            self.assertEqual(AIConfig.get_masked_api_key(), "sk-p...6789")

    def test_safe_config_summary_dict(self):
        with patch.dict(os.environ, {"AI_API_KEY": "secret_key_12345"}, clear=True):
            summary = AIConfig.to_dict()
            self.assertTrue(summary["is_configured"])
            self.assertNotIn("secret_key_12345", str(summary))
            self.assertIn("masked_key", summary)

    def test_provider_key_isolation_google(self):
        # When provider is google, OPENAI_API_KEY must not be used
        env = {
            "AI_PROVIDER": "google",
            "OPENAI_API_KEY": "sk-openai-secret",
            "GEMINI_API_KEY": "gemini-secret-123",
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(AIConfig.get_api_key(), "gemini-secret-123")
            self.assertEqual(AIConfig.get_api_key("google"), "gemini-secret-123")

    def test_provider_key_isolation_openai(self):
        # When provider is openai, GEMINI_API_KEY must not be used
        env = {
            "AI_PROVIDER": "openai",
            "GEMINI_API_KEY": "gemini-secret-123",
            "OPENAI_API_KEY": "sk-openai-secret",
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(AIConfig.get_api_key(), "sk-openai-secret")
            self.assertEqual(AIConfig.get_api_key("openai"), "sk-openai-secret")

    def test_openai_auto_detection(self):
        # When AI_PROVIDER is unset but OPENAI_API_KEY is present
        env = {
            "OPENAI_API_KEY": "sk-openai-secret",
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(AIConfig.get_provider(), "openai")
            self.assertEqual(AIConfig.get_api_key(), "sk-openai-secret")


class TestAIExceptions(unittest.TestCase):
    """Test AI exception hierarchy and user-safe messaging."""

    def test_exception_inheritance(self):
        from ai.exceptions import AIRequestError, AIModelNotFoundError
        self.assertTrue(issubclass(AIConfigurationError, AIError))
        self.assertTrue(issubclass(AIAuthenticationError, AIError))
        self.assertTrue(issubclass(AIRateLimitError, AIError))
        self.assertTrue(issubclass(AITimeoutError, AIError))
        self.assertTrue(issubclass(AIProviderError, AIError))
        self.assertTrue(issubclass(AIInvalidResponseError, AIError))
        self.assertTrue(issubclass(AIRequestError, AIError))
        self.assertTrue(issubclass(AIModelNotFoundError, AIError))

    def test_user_safe_message_default(self):
        err = AIError("Internal stack details that should not reach user")
        self.assertIn("temporarily unavailable", err.user_safe_message)


class TestAIClientFactory(unittest.TestCase):
    """Test AI client initialization, provider abstraction, and fallback safety."""

    def test_unconfigured_defaults_to_mock_without_crashing(self):
        with patch.dict(os.environ, {"AI_API_KEY": ""}, clear=True):
            client = get_ai_client(require_configured=False)
            self.assertIsInstance(client, MockAIProvider)
            self.assertEqual(
                client.generate_text("hello"), "Mock AI text response for testing."
            )

    def test_unconfigured_raises_when_required(self):
        with patch.dict(os.environ, {"AI_API_KEY": ""}, clear=True):
            with self.assertRaises(AIConfigurationError):
                get_ai_client(require_configured=True)

    def test_configured_google_provider(self):
        env = {
            "AI_PROVIDER": "google",
            "AI_API_KEY": "valid_test_api_key",
            "AI_MODEL": "gemini-3.6-flash",
        }
        with patch.dict(os.environ, env, clear=True):
            client = get_ai_client()
            self.assertIsInstance(client, GoogleGeminiProvider)
            self.assertEqual(client.model, "gemini-3.6-flash")
            self.assertEqual(
                client._get_url(),
                "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent"
            )
            self.assertNotIn("?key=", client._get_url())

    def test_configured_openai_provider(self):
        env = {
            "AI_PROVIDER": "openai",
            "AI_API_KEY": "valid_test_api_key",
            "AI_MODEL": "gpt-4o",
        }
        with patch.dict(os.environ, env, clear=True):
            client = get_ai_client()
            self.assertIsInstance(client, OpenAIProvider)
            self.assertEqual(client.model, "gpt-4o")


class TestAIServiceStubs(unittest.TestCase):
    """Test service interfaces and structured response formatters."""

    def test_format_ai_response(self):
        ok = format_ai_response(True, data={"test": 1})
        self.assertTrue(ok["success"])
        self.assertEqual(ok["data"], {"test": 1})
        self.assertIsNone(ok["error"])

        fail = format_ai_response(False, error="Error message")
        self.assertFalse(fail["success"])
        self.assertIsNone(fail["data"])
        self.assertEqual(fail["error"], "Error message")

    def test_vision_stub_interface(self):
        with patch.dict(os.environ, {"AI_PROVIDER": "mock", "AI_API_KEY": "test"}, clear=True):
            res = analyze_item_image("data:image/png;base64,mock")
            self.assertTrue(res["success"])
            self.assertIn("category", res["data"])
            self.assertIn("primary_color", res["data"])

    def test_matching_stub_interface(self):
        res = find_potential_matches({"name": "Keys"}, [{"name": "Keychain"}])
        self.assertTrue(res["success"])
        self.assertIn("matches", res["data"])

    def test_search_stub_interface(self):
        res = semantic_search("black wallet", [])
        self.assertTrue(res["success"])
        self.assertIn("results", res["data"])

    def test_claim_stub_interface(self):
        res = analyze_claim(
            {"proof_description": "Blue lanyard with student ID"},
            {"secret_detail": "Blue lanyard"},
        )
        self.assertTrue(res["success"])
        self.assertIn("confidence_score", res["data"])
        self.assertIn("recommendation", res["data"])


if __name__ == "__main__":
    unittest.main()
