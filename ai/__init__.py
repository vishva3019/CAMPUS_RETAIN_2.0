"""Campus Retain AI Service Layer.

Intelligent campus lost & found AI subsystem providing image analysis,
lost-and-found match scoring, natural language semantic search, and
claim verification assistance.
"""

from __future__ import annotations

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
from ai.client import (
    BaseAIProvider,
    GoogleGeminiProvider,
    MockAIProvider,
    OpenAIProvider,
    format_ai_response,
    get_ai_client,
)
from ai.vision import analyze_item_image
from ai.matching import find_potential_matches
from ai.search import semantic_search
from ai.claims import analyze_claim

__all__ = [
    "AIConfig",
    "AIError",
    "AIConfigurationError",
    "AIAuthenticationError",
    "AIRateLimitError",
    "AITimeoutError",
    "AIProviderError",
    "AIInvalidResponseError",
    "BaseAIProvider",
    "GoogleGeminiProvider",
    "MockAIProvider",
    "OpenAIProvider",
    "format_ai_response",
    "get_ai_client",
    "analyze_item_image",
    "find_potential_matches",
    "semantic_search",
    "analyze_claim",
]
