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

    def __init__(self, message: str, user_safe_message: str | None = None):
        super().__init__(
            message,
            user_safe_message
            or "AI service is currently not configured. Standard features remain available.",
        )


class AIAuthenticationError(AIError):
    """Raised when the AI provider authentication fails (e.g. invalid API key)."""

    def __init__(self, message: str, user_safe_message: str | None = None):
        super().__init__(
            message,
            user_safe_message
            or "AI authentication failed. Standard features remain available.",
        )


class AIRateLimitError(AIError):
    """Raised when the AI provider returns a rate limit / 429 quota error."""

    def __init__(self, message: str, user_safe_message: str | None = None):
        super().__init__(
            message,
            user_safe_message
            or "AI rate limit reached. Please wait a moment and try again.",
        )


class AITimeoutError(AIError):
    """Raised when the AI provider request times out."""

    def __init__(self, message: str, user_safe_message: str | None = None):
        super().__init__(
            message,
            user_safe_message
            or "AI analysis timed out. Standard features remain available.",
        )


class AIProviderError(AIError):
    """Raised when the upstream AI provider returns a server error (5xx) or unexpected error."""

    def __init__(self, message: str, user_safe_message: str | None = None):
        super().__init__(
            message,
            user_safe_message
            or "AI provider is temporarily unavailable. Standard reporting is still available.",
        )


class AIInvalidResponseError(AIError):
    """Raised when the AI provider returns unparseable or schema-invalid output."""

    def __init__(self, message: str, user_safe_message: str | None = None):
        super().__init__(
            message,
            user_safe_message
            or "AI analysis response could not be parsed. Standard reporting is still available.",
        )


class AIRequestError(AIError):
    """Raised when the request parameters or payload are invalid."""

    def __init__(self, message: str, user_safe_message: str | None = None):
        super().__init__(
            message,
            user_safe_message
            or "AI image analysis request was invalid. Please try another photo.",
        )


class AIModelNotFoundError(AIError):
    """Raised when the specified AI model or endpoint cannot be found."""

    def __init__(self, message: str, user_safe_message: str | None = None):
        super().__init__(
            message,
            user_safe_message
            or "AI image analysis model is temporarily unavailable. Please try again.",
        )
