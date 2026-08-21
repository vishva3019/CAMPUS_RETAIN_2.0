"""AI Claim Verification Assistance Service Interface.

Evaluates student claim proof descriptions against finder's secret details
and item metadata to compute AI confidence and verification recommendations for admins.
Actual implementation will be added in Phase 6.
"""

from __future__ import annotations

from typing import Any

from ai.client import format_ai_response


def analyze_claim(
    claim_data: dict[str, Any], item_data: dict[str, Any]
) -> dict[str, Any]:
    """Analyze claim proof and generate confidence score and evidence breakdown.

    Actual implementation will be added in Phase 6.
    """
    return format_ai_response(
        True,
        data={
            "confidence_score": 0,
            "confidence_level": "low",
            "recommendation": "NEEDS_MANUAL_REVIEW",
            "strong_evidence": [],
            "discrepancies": [],
            "is_stub": True,
        },
    )
