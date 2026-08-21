"""AI Service Exceptions.

Structured exception hierarchy for all AI operations. Raw provider errors and
sensitive internal API credentials are never exposed through these exceptions.
"""

from __future__ import annotations


class AIError(Exception):
    """Base exception for all AI operations."""

    def __init__(self, message: str, user_safe_message: str | None = None):
        super().__init__(message)
        self.user_safe_message = (
            user_safe_message
            or "AI analysis is temporarily unavailable. Standard search and matching are still available."
        )


class AIConfigurationError(AIError):
    """Raised when AI environment variables or provider configs are invalid or missing."""


class AIAuthenticationError(AIError):
    """Raised when the AI provider authentication fails (e.g. invalid API key)."""


class AIRateLimitError(AIError):
    """Raised when the AI provider returns a rate limit / 429 quota error."""


class AITimeoutError(AIError):
    """Raised when the AI provider request times out."""


class AIProviderError(AIError):
    """Raised when the upstream AI provider returns a server error (5xx) or unexpected error."""


class AIInvalidResponseError(AIError):
    """Raised when the AI provider returns unparseable or schema-invalid output."""
