"""AI Lost/Found Matching Service Interface.

Compares lost items with registered found inventory, calculates match scores,
and generates human-readable reasoning and differences.
Actual AI matching will be implemented in Phase 4.
"""

from __future__ import annotations

from typing import Any

from ai.client import format_ai_response


def find_potential_matches(
    lost_item_data: dict[str, Any], candidate_items: list[dict[str, Any]]
) -> dict[str, Any]:
    """Compare a lost item description and image metadata against candidate found items.

    Returns ranked list of candidate matches with confidence scores and reasoning.
    Actual AI matching logic will be implemented in Phase 4.
    """
    return format_ai_response(
        True,
        data={
            "matches": [],
            "total_evaluated": len(candidate_items),
            "is_stub": True,
        },
    )
