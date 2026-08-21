"""AI Configuration Management.

Reads and validates AI provider settings from environment variables safely.
Never leaks raw credentials or cross-contaminates provider keys.
"""

from __future__ import annotations

import os


class AIConfig:
    """Centralized AI configuration container."""

    @staticmethod
    def get_provider() -> str:
        """Returns the configured AI provider, normalized to lowercase (default: 'google')."""
        provider = os.environ.get("AI_PROVIDER")
        if provider:
            return provider.strip().lower()
        # Auto-detect provider if OPENAI_API_KEY is present without Google keys
        if os.environ.get("OPENAI_API_KEY") and not (
            os.environ.get("AI_API_KEY")
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
        ):
            return "openai"
        return "google"

    @staticmethod
    def get_api_key(provider: str | None = None) -> str:
        """Returns the appropriate API key for the selected AI provider.

        Strictly isolates keys to prevent cross-provider leakage.
        """
        target_provider = (provider or AIConfig.get_provider()).lower()

        if target_provider in ("google", "gemini"):
            return (
                os.environ.get("AI_API_KEY")
                or os.environ.get("GEMINI_API_KEY")
                or os.environ.get("GOOGLE_API_KEY")
                or ""
            ).strip()
        elif target_provider in ("openai",):
            return (
                os.environ.get("OPENAI_API_KEY")
                or os.environ.get("AI_API_KEY")
                or ""
            ).strip()
        elif target_provider in ("mock", "test"):
            return (os.environ.get("AI_API_KEY") or "mock-key").strip()
        else:
            return (os.environ.get("AI_API_KEY") or "").strip()

    @staticmethod
    def get_model() -> str:
        """Returns the configured model name with a safe default."""
        provider = AIConfig.get_provider()
        default_model = (
            "gemini-2.5-flash" if provider in ("google", "gemini") else "gpt-4o-mini"
        )
        return (os.environ.get("AI_MODEL") or default_model).strip()

    @staticmethod
    def get_timeout() -> int:
        """Timeout in seconds for AI requests."""
        try:
            return int(os.environ.get("AI_TIMEOUT", "15"))
        except ValueError:
            return 15

    @classmethod
    def is_configured(cls) -> bool:
        """True if an AI API key is configured for the current provider."""
        return bool(cls.get_api_key())

    @classmethod
    def get_masked_api_key(cls) -> str:
        """Returns masked API key suitable for diagnostic logs without leaking secrets."""
        key = cls.get_api_key()
        if not key:
            return "NOT_CONFIGURED"
        if len(key) <= 8:
            return "******"
        return f"{key[:4]}...{key[-4:]}"

    @classmethod
    def to_dict(cls) -> dict:
        """Returns a safe summary dictionary of current AI configuration."""
        return {
            "provider": cls.get_provider(),
            "model": cls.get_model(),
            "is_configured": cls.is_configured(),
            "masked_key": cls.get_masked_api_key(),
            "timeout_seconds": cls.get_timeout(),
        }
