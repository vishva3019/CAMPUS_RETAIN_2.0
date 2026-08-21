"""AI Provider Abstraction and Client Interface.

Provides a pluggable base class and provider implementations so the underlying
AI service (Google Gemini, OpenAI, Mock/Stub) can be swapped without modifying
higher-level application logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import base64
import json
import logging
import re
from typing import Any

import requests

from ai.config import AIConfig
from ai.exceptions import (
    AIAuthenticationError,
    AIConfigurationError,
    AIError,
    AIInvalidResponseError,
    AIModelNotFoundError,
    AIProviderError,
    AIRateLimitError,
    AIRequestError,
    AITimeoutError,
)

logger = logging.getLogger("campusretain.ai")


def _strip_markdown_code_fence(text: str) -> str:
    """Helper to remove markdown ```json ... ``` wrapper if present in LLM response."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


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
            "category": "backpack",
            "primary_color": "black",
            "secondary_colors": ["red"],
            "brand": "Nike",
            "model": None,
            "visible_text": ["Nike"],
            "distinctive_features": ["red zipper", "Nike logo", "multiple compartments"],
            "condition": "good",
            "confidence": 0.92,
        }


class GoogleGeminiProvider(BaseAIProvider):
    """Google Gemini AI Provider implementation using standard REST API."""

    def _get_url(self) -> str:
        # Standard Google Gemini REST endpoint
        clean_model = self.model.strip()
        if clean_model.startswith("models/"):
            clean_model = clean_model[7:]
        return f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent"

    def _execute_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = self._get_url()
        try:
            response = requests.post(
                url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": self.api_key,
                },
                timeout=self.timeout,
            )
        except requests.exceptions.Timeout as exc:
            logger.warning(f"Google Gemini request timed out: model={self.model}, timeout={self.timeout}s")
            raise AITimeoutError(
                f"Google Gemini request timed out after {self.timeout}s.",
                user_safe_message="AI analysis timed out. Please try again."
            ) from exc
        except requests.exceptions.RequestException as exc:
            logger.warning(f"Google Gemini network fault: model={self.model}, err={exc}")
            raise AIProviderError(
                f"Network communication fault with Google Gemini: {exc}",
                user_safe_message="AI provider is temporarily unavailable. Standard reporting is still available."
            ) from exc

        # Extract sanitized message from upstream error payload
        err_msg = ""
        category = "unknown"
        if response.status_code == 200:
            category = "success"
            logger.info(
                f"Gemini vision request success: provider=google, model={self.model}, "
                f"status=200, category=success"
            )
        else:
            try:
                err_body = response.json()
                err_msg = err_body.get("error", {}).get("message", response.text)
            except Exception:
                err_msg = response.text[:200]

            if response.status_code in (401, 403):
                category = "authentication_error"
            elif response.status_code == 404:
                category = "model_not_found"
            elif response.status_code == 429:
                category = "rate_limit_exceeded"
            elif response.status_code == 400:
                category = "invalid_payload_schema"
            elif response.status_code >= 500:
                category = "upstream_server_error"

            logger.warning(
                f"Gemini vision request failed: provider=google, model={self.model}, "
                f"status={response.status_code}, category={category}, msg={err_msg}"
            )

        if response.status_code in (401, 403):
            raise AIAuthenticationError(
                f"Invalid or unauthorized Google AI API key ({err_msg}).",
                user_safe_message="AI service authentication failed. Please contact the administrator."
            )
        if response.status_code == 404:
            raise AIModelNotFoundError(
                f"Google AI model '{self.model}' not found (HTTP 404): {err_msg}",
                user_safe_message="AI image analysis is temporarily unavailable. Please try again."
            )
        if response.status_code == 429:
            raise AIRateLimitError(
                "Google AI quota rate limit exceeded. Please retry in a moment.",
                user_safe_message="AI rate limit reached. Please wait a moment and try again."
            )
        if response.status_code == 400:
            raise AIRequestError(
                f"Google AI request payload invalid (HTTP 400): {err_msg}",
                user_safe_message="AI image analysis request was invalid. Please try another photo."
            )
        if response.status_code >= 500:
            raise AIProviderError(
                f"Google AI upstream server error (HTTP {response.status_code}): {err_msg}",
                user_safe_message="AI provider is temporarily unavailable. Standard reporting is still available."
            )
        if response.status_code != 200:
            raise AIProviderError(
                f"Google AI error (HTTP {response.status_code}): {err_msg}",
                user_safe_message="AI image analysis is temporarily unavailable. Please try again."
            )

        try:
            return response.json()
        except Exception as exc:
            raise AIInvalidResponseError(
                "Invalid JSON from Gemini API.",
                user_safe_message="AI analysis response could not be parsed. Standard reporting is still available."
            ) from exc

    def generate_text(self, prompt: str, system_instruction: str | None = None) -> str:
        payload: dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2},
        }
        if system_instruction:
            payload["system_instruction"] = {"parts": [{"text": system_instruction}]}

        data = self._execute_request(payload)
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except (KeyError, IndexError) as exc:
            raise AIInvalidResponseError("Malformed candidate structure from Gemini.") from exc

    def generate_json(
        self, prompt: str, system_instruction: str | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }
        if system_instruction:
            payload["system_instruction"] = {"parts": [{"text": system_instruction}]}

        data = self._execute_request(payload)
        try:
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
            cleaned = _strip_markdown_code_fence(raw_text)
            return json.loads(cleaned)
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            raise AIInvalidResponseError(
                f"Failed to parse Gemini JSON output: {exc}"
            ) from exc

    def analyze_multimodal(
        self,
        prompt: str,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        system_instruction: str | None = None,
    ) -> dict[str, Any]:
        b64_data = base64.b64encode(image_bytes).decode("utf-8")
        payload: dict[str, Any] = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inlineData": {
                                "mimeType": mime_type,
                                "data": b64_data,
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }
        if system_instruction:
            payload["system_instruction"] = {"parts": [{"text": system_instruction}]}

        data = self._execute_request(payload)
        try:
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
            cleaned = _strip_markdown_code_fence(raw_text)
            return json.loads(cleaned)
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            raise AIInvalidResponseError(
                f"Failed to parse Gemini multimodal JSON output: {exc}"
            ) from exc


class OpenAIProvider(BaseAIProvider):
    """OpenAI Provider implementation."""

    def _execute_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = requests.post(
                url, json=payload, headers=headers, timeout=self.timeout
            )
        except requests.exceptions.Timeout as exc:
            logger.warning(f"OpenAI request timed out: model={self.model}, timeout={self.timeout}s")
            raise AITimeoutError(
                f"OpenAI request timed out after {self.timeout}s.",
                user_safe_message="AI analysis timed out. Please try again."
            ) from exc
        except requests.exceptions.RequestException as exc:
            logger.warning(f"OpenAI network fault: model={self.model}, err={exc}")
            raise AIProviderError(
                f"Network error connecting to OpenAI: {exc}",
                user_safe_message="AI provider is temporarily unavailable. Standard reporting is still available."
            ) from exc

        err_msg = ""
        if response.status_code != 200:
            try:
                err_body = response.json()
                err_msg = err_body.get("error", {}).get("message", response.text)
            except Exception:
                err_msg = response.text[:200]

            logger.warning(
                f"OpenAI request failed: status={response.status_code}, "
                f"model={self.model}, msg={err_msg}"
            )

        if response.status_code in (401, 403):
            raise AIAuthenticationError(
                "Invalid or unauthorized OpenAI API key.",
                user_safe_message="AI service authentication failed. Please contact the administrator."
            )
        if response.status_code == 404:
            raise AIModelNotFoundError(
                f"OpenAI model '{self.model}' not found (HTTP 404): {err_msg}",
                user_safe_message="AI image analysis is temporarily unavailable. Please try again."
            )
        if response.status_code == 429:
            raise AIRateLimitError(
                "OpenAI rate limit quota exceeded.",
                user_safe_message="AI rate limit reached. Please wait a moment and try again."
            )
        if response.status_code == 400:
            raise AIRequestError(
                f"OpenAI request payload invalid (HTTP 400): {err_msg}",
                user_safe_message="AI image analysis request was invalid. Please try another photo."
            )
        if response.status_code >= 500:
            raise AIProviderError(
                f"OpenAI server error (HTTP {response.status_code}).",
                user_safe_message="AI provider is temporarily unavailable. Standard reporting is still available."
            )
        if response.status_code != 200:
            raise AIProviderError(
                f"OpenAI error (HTTP {response.status_code}): {err_msg}",
                user_safe_message="AI image analysis is temporarily unavailable. Please try again."
            )

        try:
            return response.json()
        except Exception as exc:
            raise AIInvalidResponseError(
                "Invalid JSON from OpenAI API.",
                user_safe_message="AI analysis response could not be parsed. Standard reporting is still available."
            ) from exc

    def generate_text(self, prompt: str, system_instruction: str | None = None) -> str:
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
        }
        data = self._execute_request(payload)
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as exc:
            raise AIInvalidResponseError("Malformed OpenAI chat completion response.") from exc

    def generate_json(
        self, prompt: str, system_instruction: str | None = None
    ) -> dict[str, Any]:
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
        }
        data = self._execute_request(payload)
        try:
            raw_text = data["choices"][0]["message"]["content"]
            cleaned = _strip_markdown_code_fence(raw_text)
            return json.loads(cleaned)
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            raise AIInvalidResponseError(
                f"Failed to parse OpenAI JSON output: {exc}"
            ) from exc

    def analyze_multimodal(
        self,
        prompt: str,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        system_instruction: str | None = None,
    ) -> dict[str, Any]:
        b64_data = base64.b64encode(image_bytes).decode("utf-8")
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{b64_data}"
                        },
                    },
                ],
            }
        )
        payload = {
            "model": self.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
        }
        data = self._execute_request(payload)
        try:
            raw_text = data["choices"][0]["message"]["content"]
            cleaned = _strip_markdown_code_fence(raw_text)
            return json.loads(cleaned)
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            raise AIInvalidResponseError(
                f"Failed to parse OpenAI multimodal JSON output: {exc}"
            ) from exc


def get_ai_client(require_configured: bool = False) -> BaseAIProvider:
    """Factory function returning the configured AI provider instance.

    If require_configured is False and no API key is present, returns a MockAIProvider
    to prevent application crashes.
    """
    provider = AIConfig.get_provider()
    key = AIConfig.get_api_key(provider)
    model = AIConfig.get_model()
    timeout = AIConfig.get_timeout()
    is_conf = bool(key)

    logger.info(
        f"AI Provider selected: {provider} | "
        f"AI configuration status: {'configured' if is_conf else 'not configured'} | "
        f"AI model: {model} | "
        f"AI key status: {'configured' if is_conf else 'missing'}"
    )

    if not is_conf:
        if require_configured:
            raise AIConfigurationError(
                f"AI service is not configured for provider '{provider}'."
            )
        return MockAIProvider(
            api_key="", model=model, timeout=timeout
        )

    if provider in ("google", "gemini"):
        return GoogleGeminiProvider(api_key=key, model=model, timeout=timeout)
    elif provider in ("openai",):
        return OpenAIProvider(api_key=key, model=model, timeout=timeout)
    elif provider in ("mock", "test"):
        return MockAIProvider(api_key=key, model=model, timeout=timeout)
    else:
        logger.warning(
            f"Unknown AI_PROVIDER '{provider}'. Falling back to GoogleGeminiProvider.",
        )
        return GoogleGeminiProvider(api_key=key, model=model, timeout=timeout)


def format_ai_response(
    success: bool, data: Any = None, error: str | None = None
) -> dict[str, Any]:
    """Standardized response formatter for all AI endpoints and services."""
    return {
        "success": success,
        "data": data if success else None,
        "error": error if not success else None,
    }
