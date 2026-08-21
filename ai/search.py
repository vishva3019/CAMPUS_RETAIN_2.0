"""AI Natural Language Search Service.

Translates free-form human queries (e.g. 'I lost my black Nike backpack near
the library yesterday') into structured search criteria, retrieves real inventory
items, and ranks them by relevance with clear match reasons.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import re
from typing import Any

from ai.client import format_ai_response, get_ai_client
from ai.config import AIConfig
from ai.exceptions import AIError
from ai.matching import (
    COLOR_FAMILIES,
    _are_colors_similar,
    _normalize_text,
    _tokenize,
    compute_deterministic_match_score,
)

logger = logging.getLogger("campusretain.ai.search")

QUERY_PARSER_SYSTEM_INSTRUCTION = """You are Campus Retain AI's Natural Language Search Assistant.
Extract structured lost-and-found search attributes from the student's query.

CRITICAL RULES:
1. DO NOT GUESS OR INVENT INFORMATION.
   - If the user does not specify a color, brand, location, or time, set that field to null.
   - Example: "I lost my phone" -> category="smartphone", brand=null, primary_color=null, location=null, time_reference=null.
2. Determine search_target:
   - If the user says "I lost", "looking for", "did anyone find", search_target is "found" (search found inventory).
   - If the user says "I found", "who lost", "picked up", search_target is "lost" (search lost reports).
   - Default search_target is "found".
3. Category normalization:
   - Normalize category to one of: smartphone, laptop, tablet, headphones, backpack, bag, wallet, keys, water bottle, clothing, jacket, shoes, book, id card, accessories, electronics, other, or null if unknown.
4. Output strictly valid JSON adhering to this schema:
{
  "category": "<string or null>",
  "brand": "<string or null>",
  "primary_color": "<string or null>",
  "location": "<string or null>",
  "time_reference": "<string or null>",
  "search_target": "<found | lost>",
  "keywords": ["<keyword1>", "<keyword2>"]
}
"""

KNOWN_CATEGORIES: dict[str, str] = {
    "phone": "smartphone",
    "iphone": "smartphone",
    "samsung": "smartphone",
    "mobile": "smartphone",
    "smartphone": "smartphone",
    "laptop": "laptop",
    "macbook": "laptop",
    "thinkpad": "laptop",
    "tablet": "tablet",
    "ipad": "tablet",
    "headphones": "headphones",
    "earbuds": "headphones",
    "airpods": "headphones",
    "charger": "charger",
    "backpack": "backpack",
    "bag": "backpack",
    "purse": "wallet",
    "wallet": "wallet",
    "keys": "keys",
    "keychain": "keys",
    "bottle": "water bottle",
    "water bottle": "water bottle",
    "flask": "water bottle",
    "card": "id card",
    "id": "id card",
    "id card": "id card",
    "book": "book",
    "notebook": "book",
    "textbook": "book",
    "jacket": "clothing",
    "hoodie": "clothing",
    "shirt": "clothing",
    "sweater": "clothing",
    "shoes": "clothing",
    "umbrella": "accessories",
    "glasses": "accessories",
    "sunglasses": "accessories",
    "watch": "accessories",
    "smartwatch": "accessories",
    "calculator": "electronics",
}

KNOWN_BRANDS: list[str] = [
    "nike", "adidas", "puma", "apple", "samsung", "lenovo", "dell", "hp", "asus",
    "sony", "bose", "jbl", "boat", "casio", "hydro flask", "wildcraft", "fastrack",
    "titan", "oneplus", "google", "xiaomi", "redmi", "logitech",
]

KNOWN_LOCATIONS: list[str] = [
    "library", "cafeteria", "canteen", "food court", "block a", "block b", "block c",
    "lab", "laboratory", "audi", "auditorium", "sports complex", "ground", "gym",
    "hostel", "mess", "main gate", "parking", "lh-101", "lh-102", "class", "classroom",
]


def deterministic_parse_query(query: str) -> dict[str, Any]:
    """Rule-based natural language query parser for instant and offline search parsing."""
    if not query:
        return {
            "category": None,
            "brand": None,
            "primary_color": None,
            "location": None,
            "time_reference": None,
            "search_target": "found",
            "keywords": [],
        }

    norm_query = _normalize_text(query)
    tokens = _tokenize(query)

    # 1. Search Target
    search_target = "found"
    if any(phrase in norm_query for phrase in ["i found a", "i found an", "i found this", "i found the", "who lost", "i picked up", "surrendered"]):
        search_target = "lost"

    # 2. Category
    category = None
    for keyword, mapped_cat in KNOWN_CATEGORIES.items():
        if keyword in norm_query or keyword in tokens:
            category = mapped_cat
            break

    # 3. Color
    primary_color = None
    for color in COLOR_FAMILIES.keys():
        if color in tokens or color in norm_query:
            primary_color = color
            break

    # 4. Brand
    brand = None
    for b in KNOWN_BRANDS:
        if b in norm_query:
            brand = b.title()
            break

    # 5. Location
    location = None
    for loc in KNOWN_LOCATIONS:
        if loc in norm_query:
            location = loc.title()
            break

    # 6. Time reference
    time_reference = None
    for t in ["yesterday", "today", "this week", "last week", "two days ago", "recently", "monday", "tuesday", "wednesday", "thursday", "friday"]:
        if t in norm_query:
            time_reference = t
            break

    # 7. Meaningful Keywords
    keywords = sorted(list(tokens))

    return {
        "category": category,
        "brand": brand,
        "primary_color": primary_color,
        "location": location,
        "time_reference": time_reference,
        "search_target": search_target,
        "keywords": keywords,
    }


def parse_natural_language_query(query: str) -> dict[str, Any]:
    """Parses a free-form query using LLM if configured, otherwise deterministic parser."""
    query = (query or "").strip()
    if not query:
        return deterministic_parse_query("")

    baseline = deterministic_parse_query(query)

    if not AIConfig.is_configured():
        return baseline

    prompt = f'User search query: "{query}"\nExtract structured lost & found search parameters in strict JSON.'

    try:
        client = get_ai_client(require_configured=True)
        res = client.generate_json(
            prompt=prompt, system_instruction=QUERY_PARSER_SYSTEM_INSTRUCTION
        )
        if isinstance(res, dict):
            category = res.get("category")
            if isinstance(category, str) and category.lower() in ("null", "none", "unknown", ""):
                category = None

            brand = res.get("brand")
            if isinstance(brand, str) and brand.lower() in ("null", "none", "unknown", ""):
                brand = None

            primary_color = res.get("primary_color")
            if isinstance(primary_color, str) and primary_color.lower() in ("null", "none", "unknown", ""):
                primary_color = None

            location = res.get("location")
            if isinstance(location, str) and location.lower() in ("null", "none", "unknown", ""):
                location = None

            time_ref = res.get("time_reference")
            if isinstance(time_ref, str) and time_ref.lower() in ("null", "none", "unknown", ""):
                time_ref = None

            target = str(res.get("search_target") or "found").lower()
            if target not in ("found", "lost"):
                target = "found"

            keywords = res.get("keywords")
            if not isinstance(keywords, list) or not keywords:
                keywords = baseline["keywords"]

            return {
                "category": category or baseline["category"],
                "brand": brand or baseline["brand"],
                "primary_color": primary_color or baseline["primary_color"],
                "location": location or baseline["location"],
                "time_reference": time_ref or baseline["time_reference"],
                "search_target": target,
                "keywords": keywords,
            }
    except AIError as exc:
        logger.warning(f"AI query parsing failed ({exc}), using deterministic parser.")
    except Exception as exc:
        logger.warning(f"Unexpected query parsing error ({exc}), using deterministic parser.")

    return baseline


def rank_search_results(
    query_understanding: dict[str, Any],
    candidate_items: list[dict[str, Any]],
    top_n: int = 15,
) -> list[dict[str, Any]]:
    """Ranks candidate items based on natural language query attributes."""
    if not candidate_items:
        return []

    # Construct virtual target representation from parsed query
    virtual_target: dict[str, Any] = {
        "name": " ".join(filter(None, [
            query_understanding.get("primary_color"),
            query_understanding.get("brand"),
            query_understanding.get("category"),
            " ".join(query_understanding.get("keywords", [])),
        ])),
        "category": query_understanding.get("category") or "Other",
        "ai_category": query_understanding.get("category"),
        "ai_primary_color": query_understanding.get("primary_color"),
        "ai_brand": query_understanding.get("brand"),
        "location": query_understanding.get("location") or "",
        "secret_detail": "",
        "ai_distinctive_features": [],
    }

    # If time reference provided, compute approximate date
    time_ref = (query_understanding.get("time_reference") or "").lower()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if "yesterday" in time_ref:
        virtual_target["date_found"] = now - timedelta(days=1)
    elif "today" in time_ref:
        virtual_target["date_found"] = now
    elif "last week" in time_ref:
        virtual_target["date_found"] = now - timedelta(days=7)
    elif "two days ago" in time_ref:
        virtual_target["date_found"] = now - timedelta(days=2)

    scored_results = []
    for cand in candidate_items:
        score, conf, matches, diffs, expl = compute_deterministic_match_score(
            virtual_target, cand
        )

        # Keyword boost: direct presence of search keywords in item title/location
        cand_text = _normalize_text(f"{cand.get('name') or ''} {cand.get('location') or ''} {cand.get('category') or ''}")
        matched_kw_count = sum(1 for kw in query_understanding.get("keywords", []) if kw.lower() in cand_text)
        if matched_kw_count > 0:
            score = min(100, score + (matched_kw_count * 5))

        # Check if item meets minimum relevance (≥ 30%)
        if score >= 30:
            relevance_label = (
                "High Relevance" if score >= 80 else ("Relevant" if score >= 60 else "Possible Match")
            )
            scored_results.append(
                {
                    "id": cand.get("id"),
                    "name": cand.get("name"),
                    "category": cand.get("category"),
                    "location": cand.get("location"),
                    "image_data": cand.get("image_data") or cand.get("image_url"),
                    "status": cand.get("status", "Available"),
                    "item_type": cand.get("item_type", "found"),
                    "date_found": str(cand.get("date_found"))[:10] if cand.get("date_found") else None,
                    "relevance_score": score,
                    "confidence": conf,
                    "relevance_label": relevance_label,
                    "matching_attributes": matches,
                    "differences": diffs,
                    "explanation": expl,
                }
            )

    # Sort descending by relevance score
    scored_results.sort(key=lambda x: x["relevance_score"], reverse=True)
    return scored_results[:top_n]


def semantic_search(query: str, items: list[dict[str, Any]], top_n: int = 15) -> dict[str, Any]:
    """Executes end-to-end natural language search over inventory."""
    query = (query or "").strip()
    if not query:
        return format_ai_response(False, error="Search query cannot be empty.")

    # 1. Parse natural language query into structured criteria
    query_understanding = parse_natural_language_query(query)

    # 2. Filter candidate pool by target type if appropriate
    target_type = query_understanding.get("search_target", "found")
    filtered_candidates = [
        item for item in items
        if (item.get("item_type") or "found") == target_type or target_type == "all"
    ]

    # If no items match target type, fallback to all items
    if not filtered_candidates:
        filtered_candidates = items

    # 3. Rank results using multi-factor relevance scoring
    ranked_results = rank_search_results(query_understanding, filtered_candidates, top_n=top_n)

    return format_ai_response(
        True,
        data={
            "query": query,
            "query_understanding": query_understanding,
            "total_candidates": len(filtered_candidates),
            "results": ranked_results,
        },
    )
