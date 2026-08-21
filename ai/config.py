"""AI Configuration Management.

Reads and validates AI provider settings from environment variables safely.
Never leaks raw credentials.
"""

from __future__ import annotations

import os


class AIConfig:
    """Centralized AI configuration container."""

    @staticmethod
    def get_provider() -> str:
        """Returns the configured AI provider, normalized to lowercase (default: 'google')."""
        return (os.environ.get("AI_PROVIDER") or "google").strip().lower()

    @staticmethod
    def get_api_key() -> str:
        """Returns the AI API key or empty string if not configured."""
        return (os.environ.get("AI_API_KEY") or "").strip()

    @staticmethod
    def get_model() -> str:
        """Returns the configured model name with a safe default."""
        provider = AIConfig.get_provider()
        default_model = (
            "gemini-1.5-flash" if provider in ("google", "gemini") else "gpt-4o-mini"
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
        """True if an AI API key is configured."""
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
