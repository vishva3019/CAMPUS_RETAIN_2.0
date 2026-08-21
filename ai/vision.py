"""AI Vision Service.

Multimodal image analysis for campus lost and found items.
Extracts category, colors, brand, model, visible text, distinctive features,
condition, and confidence score without hallucinating or inventing details.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from ai.client import format_ai_response, get_ai_client
from ai.exceptions import AIError

logger = logging.getLogger("campusretain.ai.vision")

MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5MB
ALLOWED_IMAGE_TYPES = {"png", "jpg", "jpeg", "webp", "gif"}
VALID_CONDITIONS = {"new", "good", "used", "damaged", "unknown"}

VISION_SYSTEM_INSTRUCTION = """You are Campus Retain AI's computer vision system.
Analyze the lost or found campus item in the provided image with high precision and objectivity.

Extract ONLY what is directly visible in the image.
Do NOT invent, assume, or hallucinate brands, models, text, serial numbers, locations, or owner details.
If a field is not clearly visible or cannot be determined, set it to null or an empty array.

Return ONLY valid JSON adhering strictly to this schema:
{
  "category": "<lowercase item category, e.g. smartphone, laptop, backpack, wallet, water bottle, headphones, keys, id card, clothing, accessories, books, watch, glasses, other>",
  "primary_color": "<dominant visible color in lowercase, e.g. black, blue, silver, red>",
  "secondary_colors": ["<other visible colors in lowercase>"],
  "brand": "<exact brand name if clearly visible (e.g. Nike, Apple, Samsung), otherwise null>",
  "model": "<specific model name if visibly printed or unmistakably recognizable, otherwise null>",
  "visible_text": ["<exact text visibly printed or written on the item>"],
  "distinctive_features": ["<specific identifying visual characteristics, e.g. red zipper, sticker on lid, scratch on corner>"],
  "condition": "<new | good | used | damaged | unknown>",
  "confidence": <float between 0.0 and 1.0 reflecting image clarity and certainty>
}"""

VISION_USER_PROMPT = """Analyze this lost/found campus item and output structured JSON matching the required schema."""


def sniff_image_mime(head: bytes) -> tuple[str, str] | None:
    """Identify image MIME type and format from leading magic bytes."""
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif", "gif"
    if head.startswith(b"RIFF") and len(head) >= 12 and head[8:12] == b"WEBP":
        return "image/webp", "webp"
    return None


def validate_and_extract_image_bytes(image_input: Any) -> tuple[bytes, str, str]:
    """Validates and extracts raw image bytes and MIME type from various input formats.

    Supports:
    - bytes
    - Data URI strings: 'data:image/jpeg;base64,...'
    - Base64 string
    - FileStorage / file-like objects with a .read() method
    """
    if image_input is None:
        raise AIError("No image data supplied.", "Please upload an image to analyze.")

    raw_bytes: bytes = b""
    explicit_mime: str | None = None

    # Case 1: Werkzeug FileStorage / file object
    if hasattr(image_input, "read"):
        if hasattr(image_input, "seek"):
            image_input.seek(0)
        raw_bytes = image_input.read()
        if hasattr(image_input, "seek"):
            image_input.seek(0)
        if hasattr(image_input, "content_type") and image_input.content_type:
            explicit_mime = image_input.content_type

    # Case 2: String (Data URL or base64)
    elif isinstance(image_input, str):
        cleaned_str = image_input.strip()
        if not cleaned_str:
            raise AIError("Image string is empty.", "The provided image data is empty.")
        if cleaned_str.startswith("data:"):
            try:
                header, b64_part = cleaned_str.split(",", 1)
                raw_bytes = base64.b64decode(b64_part)
                if ";" in header:
                    explicit_mime = header.split(";", 1)[0].replace("data:", "").strip()
            except Exception as exc:
                raise AIError(
                    f"Malformed image data URI: {exc}", "Invalid image format uploaded."
                ) from exc
        else:
            try:
                raw_bytes = base64.b64decode(cleaned_str)
            except Exception as exc:
                raise AIError(
                    f"Malformed base64 image data: {exc}", "Invalid image encoding."
                ) from exc

    # Case 3: Raw bytes
    elif isinstance(image_input, (bytes, bytearray)):
        raw_bytes = bytes(image_input)
    else:
        raise AIError(
            f"Unsupported image input type: {type(image_input)}",
            "Unsupported image format.",
        )

    if not raw_bytes:
        raise AIError("Image payload is 0 bytes.", "The uploaded image file is empty.")

    if len(raw_bytes) > MAX_IMAGE_SIZE_BYTES:
        raise AIError(
            f"Image exceeds maximum size ({len(raw_bytes)} > {MAX_IMAGE_SIZE_BYTES})",
            "Image exceeds the 5MB size limit. Please upload a smaller photo.",
        )

    sniffed = sniff_image_mime(raw_bytes[:32])
    if sniffed is None:
        if explicit_mime and explicit_mime in ("image/jpeg", "image/png", "image/webp", "image/gif"):
            mime_type = explicit_mime
            ext = explicit_mime.split("/")[-1]
        else:
            raise AIError(
                "Uploaded file is not a supported image format.",
                "Please upload a valid PNG, JPEG, WEBP, or GIF image.",
            )
    else:
        mime_type, ext = sniffed

    return raw_bytes, mime_type, ext


def normalize_ai_vision_output(raw_data: dict[str, Any]) -> dict[str, Any]:
    """Validates, cleans, and normalizes AI-extracted vision metadata against schema."""
    if not isinstance(raw_data, dict):
        raw_data = {}

    category = str(raw_data.get("category") or "other").strip().lower()
    primary_color = str(raw_data.get("primary_color") or "unknown").strip().lower()

    # Secondary colors list
    raw_secondary = raw_data.get("secondary_colors")
    secondary_colors = []
    if isinstance(raw_secondary, list):
        for c in raw_secondary:
            if isinstance(c, str) and c.strip():
                secondary_colors.append(c.strip().lower())

    # Brand
    brand_val = raw_data.get("brand")
    brand = str(brand_val).strip() if brand_val and str(brand_val).lower() not in ("null", "none", "unknown", "") else None

    # Model
    model_val = raw_data.get("model")
    model = str(model_val).strip() if model_val and str(model_val).lower() not in ("null", "none", "unknown", "") else None

    # Visible text list
    raw_text = raw_data.get("visible_text")
    visible_text = []
    if isinstance(raw_text, list):
        for t in raw_text:
            if isinstance(t, str) and t.strip():
                visible_text.append(t.strip())

    # Distinctive features list
    raw_features = raw_data.get("distinctive_features")
    distinctive_features = []
    if isinstance(raw_features, list):
        for f in raw_features:
            if isinstance(f, str) and f.strip():
                distinctive_features.append(f.strip())

    # Condition
    cond_raw = str(raw_data.get("condition") or "unknown").strip().lower()
    condition = cond_raw if cond_raw in VALID_CONDITIONS else "unknown"

    # Confidence
    conf_raw = raw_data.get("confidence")
    try:
        confidence = float(conf_raw)
        confidence = max(0.0, min(1.0, round(confidence, 2)))
    except (TypeError, ValueError):
        confidence = 0.85

    return {
        "category": category,
        "primary_color": primary_color,
        "secondary_colors": secondary_colors,
        "brand": brand,
        "model": model,
        "visible_text": visible_text,
        "distinctive_features": distinctive_features,
        "condition": condition,
        "confidence": confidence,
    }


def analyze_item_image(image_input: Any) -> dict[str, Any]:
    """Analyze a lost/found item image using multimodal AI.

    Validates the image, executes the vision model, validates output JSON,
    and returns normalized structured metadata.
    """
    try:
        raw_bytes, mime_type, _ext = validate_and_extract_image_bytes(image_input)
    except AIError as exc:
        return format_ai_response(False, error=exc.user_safe_message)
    except Exception as exc:
        logger.exception("Unexpected error during image validation")
        return format_ai_response(
            False, error="Image validation failed. Please try a different photo."
        )

    try:
        client = get_ai_client(require_configured=True)
        raw_response = client.analyze_multimodal(
            prompt=VISION_USER_PROMPT,
            image_bytes=raw_bytes,
            mime_type=mime_type,
            system_instruction=VISION_SYSTEM_INSTRUCTION,
        )
        normalized = normalize_ai_vision_output(raw_response)
        return format_ai_response(True, data=normalized)

    except AIError as exc:
        logger.warning(f"AI vision analysis failed with AIError: {exc}")
        return format_ai_response(False, error=exc.user_safe_message)
    except Exception as exc:
        logger.exception(f"Unexpected AI vision error: {exc}")
        return format_ai_response(
            False,
            error="AI analysis failed. Please try again.",
        )
