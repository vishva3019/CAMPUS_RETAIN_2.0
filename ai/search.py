"""AI Natural Language Search Service Interface.

Parses free-form natural language lost item descriptions (e.g. 'I lost a black
Samsung phone near the library yesterday') and ranks database records by relevance.
Actual implementation will be added in Phase 5.
"""

from __future__ import annotations

from typing import Any

from ai.client import format_ai_response


def semantic_search(query: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    """Search inventory using natural language query understanding.

    Actual implementation will be added in Phase 5.
    """
    if not query or not query.strip():
        return format_ai_response(False, error="Search query cannot be empty.")

    return format_ai_response(
        True,
        data={
            "query": query.strip(),
            "extracted_entities": {},
            "results": [],
            "is_stub": True,
        },
    )
