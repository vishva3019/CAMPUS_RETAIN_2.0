"""AI Vision Service Interface.

Module for multimodal image analysis of lost and found items.
Actual AI analysis implementation will be added in Phase 3.
"""

from __future__ import annotations

from typing import Any

from ai.client import format_ai_response


def analyze_item_image(image_data: str | bytes | None) -> dict[str, Any]:
    """Analyze a lost/found item image and extract structured attributes.

    Extracts category, primary/secondary colors, brand, model, visible text,
    distinctive features, accessories, and damage/marks.

    Actual AI implementation will be added in Phase 3.
    """
    if not image_data:
        return format_ai_response(False, error="No image data provided for analysis.")

    return format_ai_response(
        True,
        data={
            "category": "Other",
            "primary_color": "Unknown",
            "secondary_colors": [],
            "brand": None,
            "model": None,
            "visible_text": [],
            "distinctive_features": [],
            "accessories": [],
            "damage_marks": None,
            "is_stub": True,
        },
    )
