"""AI Provider Abstraction and Client Interface.

Provides a pluggable base class and provider implementations so the underlying
AI service (Google Gemini, OpenAI, Mock/Stub) can be swapped without modifying
higher-level application logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import logging
from typing import Any

from ai.config import AIConfig
from ai.exceptions import (
    AIAuthenticationError,
    AIConfigurationError,
    AIError,
    AIInvalidResponseError,
    AIProviderError,
    AIRateLimitError,
    AITimeoutError,
)

logger = logging.getLogger("campusretain.ai")


class BaseAIProvider(ABC):
    """Abstract interface for AI service providers."""

    def __init__(self, api_key: str, model: str, timeout: int = 15):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    @abstractmethod
    def generate_text(self, prompt: str, system_instruction: str | None = None) -> str:
        """Generate a text completion for the given prompt."""
        raise NotImplementedError

    @abstractmethod
    def generate_json(
        self, prompt: str, system_instruction: str | None = None
    ) -> dict[str, Any]:
        """Generate and parse structured JSON for the given prompt."""
        raise NotImplementedError

    @abstractmethod
    def analyze_multimodal(
        self,
        prompt: str,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        system_instruction: str | None = None,
    ) -> dict[str, Any]:
        """Analyze an image alongside text instructions and return structured JSON."""
        raise NotImplementedError


class MockAIProvider(BaseAIProvider):
    """Mock/Fallback provider used in tests or when AI is unconfigured."""

    def generate_text(self, prompt: str, system_instruction: str | None = None) -> str:
        return "Mock AI text response for testing."

    def generate_json(
        self, prompt: str, system_instruction: str | None = None
    ) -> dict[str, Any]:
        return {"mock": True, "message": "Mock structured response"}

    def analyze_multimodal(
        self,
        prompt: str,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        system_instruction: str | None = None,
    ) -> dict[str, Any]:
        return {
            "category": "Other",
            "primary_color": "Unknown",
            "secondary_colors": [],
            "brand": None,
            "model": None,
            "visible_text": [],
            "distinctive_features": [],
        }


class GoogleGeminiProvider(BaseAIProvider):
    """Google Gemini AI Provider implementation using REST API."""

    def generate_text(self, prompt: str, system_instruction: str | None = None) -> str:
        raise NotImplementedError(
            "Real AI API generation will be enabled in feature phases."
        )

    def generate_json(
        self, prompt: str, system_instruction: str | None = None
    ) -> dict[str, Any]:
        raise NotImplementedError(
            "Real AI API generation will be enabled in feature phases."
        )

    def analyze_multimodal(
        self,
        prompt: str,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        system_instruction: str | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError(
            "Real AI Multimodal analysis will be enabled in Phase 3."
        )


class OpenAIProvider(BaseAIProvider):
    """OpenAI Provider implementation."""

    def generate_text(self, prompt: str, system_instruction: str | None = None) -> str:
        raise NotImplementedError(
            "Real AI API generation will be enabled in feature phases."
        )

    def generate_json(
        self, prompt: str, system_instruction: str | None = None
    ) -> dict[str, Any]:
        raise NotImplementedError(
            "Real AI API generation will be enabled in feature phases."
        )

    def analyze_multimodal(
        self,
        prompt: str,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        system_instruction: str | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError(
            "Real AI Multimodal analysis will be enabled in Phase 3."
        )


def get_ai_client(require_configured: bool = False) -> BaseAIProvider:
    """Factory function returning the configured AI provider instance.

    If require_configured is False and no API key is present, returns a MockAIProvider
    to prevent application crashes.
    """
    if not AIConfig.is_configured():
        if require_configured:
            raise AIConfigurationError(
                "AI_API_KEY environment variable is not configured."
            )
        return MockAIProvider(
            api_key="", model=AIConfig.get_model(), timeout=AIConfig.get_timeout()
        )

    provider = AIConfig.get_provider()
    key = AIConfig.get_api_key()
    model = AIConfig.get_model()
    timeout = AIConfig.get_timeout()

    if provider in ("google", "gemini"):
        return GoogleGeminiProvider(api_key=key, model=model, timeout=timeout)
    elif provider in ("openai",):
        return OpenAIProvider(api_key=key, model=model, timeout=timeout)
    elif provider in ("mock", "test"):
        return MockAIProvider(api_key=key, model=model, timeout=timeout)
    else:
        logger.warning(
            "Unknown AI_PROVIDER '%s'. Falling back to MockAIProvider.", provider
        )
        return MockAIProvider(api_key=key, model=model, timeout=timeout)


def format_ai_response(
    success: bool, data: Any = None, error: str | None = None
) -> dict[str, Any]:
    """Standardized response formatter for all AI endpoints and services."""
    return {
        "success": success,
        "data": data if success else None,
        "error": error if not success else None,
    }
