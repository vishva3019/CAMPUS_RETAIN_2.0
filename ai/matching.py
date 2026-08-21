"""AI Lost & Found Matching Engine.

Intelligent matching engine that identifies, ranks, and explains potential
matches between lost item reports and found item reports using:
- Category, color, brand, and model
- Name, description, and keyword overlap
- AI image metadata and distinctive features
- Location and time proximity
- Multimodal LLM semantic reasoning with deterministic fallback
"""

from __future__ import annotations

from datetime import datetime
import logging
import re
from typing import Any

from ai.client import format_ai_response, get_ai_client
from ai.config import AIConfig
from ai.exceptions import AIError

logger = logging.getLogger("campusretain.ai.matching")

# Color similarity families
COLOR_FAMILIES = {
    "black": {"black", "dark grey", "charcoal", "dark"},
    "blue": {"blue", "navy", "cyan", "sky blue", "teal"},
    "grey": {"grey", "gray", "silver", "metallic", "charcoal"},
    "white": {"white", "off-white", "cream", "ivory", "beige"},
    "red": {"red", "maroon", "crimson", "burgundy", "pink"},
    "green": {"green", "olive", "lime", "emerald"},
    "brown": {"brown", "tan", "khaki", "coffee"},
    "yellow": {"yellow", "gold", "amber", "mustard"},
    "orange": {"orange", "peach", "coral"},
    "purple": {"purple", "violet", "lavender", "magenta"},
}

MATCHING_SYSTEM_INSTRUCTION = """You are Campus Retain AI's Lost & Found matching specialist.
Evaluate whether two campus item reports (one lost, one found) could refer to the same physical object.

Rules:
- Be realistic and objective. Never claim certainty. Use terms like "potential match", "likely match".
- Compare category, colors, brand, model, visible text, distinctive features, locations, and time proximity.
- Highlight specific matching attributes and clear differences.
- Output ONLY valid JSON adhering strictly to this schema:
{
  "match_score": <int between 0 and 100>,
  "confidence": "<high | medium | low>",
  "matching_attributes": ["<specific matching attribute 1>", "<specific matching attribute 2>"],
  "differences": ["<specific difference 1>"],
  "explanation": "<1-2 sentence neutral summary explaining why this is a potential match or why differences exist>"
}
- Confidence guide: 80-100: "high", 60-79: "medium", 40-59: "low", <40: "low".
"""


def _normalize_text(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"[^\w\s]", " ", text.lower()).strip()


def _tokenize(text: str | None) -> set[str]:
    norm = _normalize_text(text)
    if not norm:
        return set()
    stopwords = {"a", "an", "the", "in", "on", "at", "near", "with", "and", "or", "of", "my", "is", "it"}
    return {w for w in norm.split() if w not in stopwords and len(w) > 1}


def _are_colors_similar(c1: str | None, c2: str | None) -> tuple[bool, bool]:
    """Returns (exact_match, similar_family_match)."""
    if not c1 or not c2 or c1 == "unknown" or c2 == "unknown":
        return False, False
    c1 = c1.strip().lower()
    c2 = c2.strip().lower()
    if c1 == c2:
        return True, True
    for family in COLOR_FAMILIES.values():
        if c1 in family and c2 in family:
            return False, True
    return False, False


def compute_deterministic_match_score(
    target: dict[str, Any], candidate: dict[str, Any]
) -> tuple[int, str, list[str], list[str], str]:
    """Computes a deterministic baseline match score (0-100) and extracted evidence.

    Returns: (score, confidence_level, matching_attributes, differences, explanation)
    """
    matching_attributes: list[str] = []
    differences: list[str] = []
    total_score = 0

    # 1. Category comparison (25 pts)
    t_cat = (target.get("ai_category") or target.get("category") or "").strip().lower()
    c_cat = (candidate.get("ai_category") or candidate.get("category") or "").strip().lower()

    if t_cat and c_cat:
        if t_cat == c_cat:
            total_score += 25
            matching_attributes.append(f"Same item category ({t_cat.title()})")
        elif t_cat in c_cat or c_cat in t_cat:
            total_score += 20
            matching_attributes.append(f"Similar category ({t_cat.title()} / {c_cat.title()})")
        else:
            differences.append(f"Different categories ({t_cat.title()} vs {c_cat.title()})")
    else:
        total_score += 10

    # 2. Color comparison (20 pts)
    t_color = (target.get("ai_primary_color") or "").strip().lower()
    c_color = (candidate.get("ai_primary_color") or "").strip().lower()

    t_combined_text = f"{target.get('name') or ''} {target.get('secret_detail') or ''}"
    c_combined_text = f"{candidate.get('name') or ''} {candidate.get('secret_detail') or ''}"
    t_tokens = _tokenize(t_combined_text)
    c_tokens = _tokenize(c_combined_text)

    if t_color and c_color and t_color != "unknown" and c_color != "unknown":
        exact, similar = _are_colors_similar(t_color, c_color)
        if exact:
            total_score += 20
            matching_attributes.append(f"Same primary color ({t_color.title()})")
        elif similar:
            total_score += 15
            matching_attributes.append(f"Similar color shade ({t_color.title()} / {c_color.title()})")
        else:
            differences.append(f"Different reported colors ({t_color.title()} vs {c_color.title()})")
    else:
        # Check if color is in name/description
        found_color_match = False
        for color in COLOR_FAMILIES.keys():
            if color in t_tokens and color in c_tokens:
                total_score += 18
                matching_attributes.append(f"Same color mentioned in report ({color.title()})")
                found_color_match = True
                break
        if not found_color_match:
            total_score += 8

    # 3. Brand / Model comparison (15 pts)
    t_brand = (target.get("ai_brand") or "").strip()
    c_brand = (candidate.get("ai_brand") or "").strip()

    if t_brand and c_brand and t_brand.lower() != "null" and c_brand.lower() != "null":
        if t_brand.lower() == c_brand.lower():
            total_score += 15
            matching_attributes.append(f"Same brand ({t_brand})")
        else:
            differences.append(f"Different identified brands ({t_brand} vs {c_brand})")
    else:
        # Check brand keywords in text
        t_norm_name = _normalize_text(target.get("name") or "")
        c_norm_name = _normalize_text(candidate.get("name") or "")
        if t_brand and t_brand.lower() in c_norm_name:
            total_score += 12
            matching_attributes.append(f"Brand '{t_brand}' identified in reports")
        elif c_brand and c_brand.lower() in t_norm_name:
            total_score += 12
            matching_attributes.append(f"Brand '{c_brand}' identified in reports")
        else:
            total_score += 7  # Neutral

    # 4. Keyword & Name semantic overlap (20 pts)
    common_tokens = t_tokens.intersection(c_tokens)
    if common_tokens:
        overlap_score = min(20, len(common_tokens) * 6)
        total_score += overlap_score
        matching_attributes.append(
            f"Matching descriptive keywords: {', '.join(sorted(list(common_tokens))[:3])}"
        )
    else:
        total_score += 2

    # 5. Distinctive visual features (10 pts)
    t_features = target.get("ai_distinctive_features") or []
    c_features = candidate.get("ai_distinctive_features") or []
    if isinstance(t_features, list) and isinstance(c_features, list) and t_features and c_features:
        t_feat_tokens = _tokenize(" ".join(t_features))
        c_feat_tokens = _tokenize(" ".join(c_features))
        shared_feat = t_feat_tokens.intersection(c_feat_tokens)
        if shared_feat:
            total_score += 10
            matching_attributes.append(
                f"Matching distinctive feature: {', '.join(sorted(list(shared_feat))[:2])}"
            )
        else:
            total_score += 4
    else:
        total_score += 5

    # 6. Location comparison (5 pts)
    t_loc = _normalize_text(target.get("location", ""))
    c_loc = _normalize_text(candidate.get("location", ""))
    if t_loc and c_loc:
        t_loc_tokens = _tokenize(t_loc)
        c_loc_tokens = _tokenize(c_loc)
        if t_loc == c_loc:
            total_score += 5
            matching_attributes.append(f"Same location ({target.get('location')})")
        elif t_loc_tokens.intersection(c_loc_tokens):
            total_score += 4
            matching_attributes.append("Similar campus area / building location")
        else:
            total_score += 1
            differences.append(
                f"Different reported locations: '{target.get('location')}' vs '{candidate.get('location')}'"
            )
    else:
        total_score += 3

    # 7. Date proximity (5 pts)
    t_date = target.get("date_found") or target.get("created_at")
    c_date = candidate.get("date_found") or candidate.get("created_at")
    if isinstance(t_date, str):
        try:
            t_date = datetime.fromisoformat(t_date.replace("Z", "+00:00"))
        except Exception:
            t_date = None
    if isinstance(c_date, str):
        try:
            c_date = datetime.fromisoformat(c_date.replace("Z", "+00:00"))
        except Exception:
            c_date = None

    if t_date and c_date:
        try:
            days_diff = abs((t_date - c_date).days)
            if days_diff <= 2:
                total_score += 5
                matching_attributes.append("Reported within 48 hours of each other")
            elif days_diff <= 7:
                total_score += 4
                matching_attributes.append("Reported within the same week")
            elif days_diff <= 14:
                total_score += 3
            else:
                total_score += 1
                differences.append(f"Reports separated by {days_diff} days")
        except Exception:
            total_score += 3
    else:
        total_score += 3

    # Clamp total score
    score = max(0, min(100, total_score))

    if score >= 80:
        confidence = "high"
    elif score >= 60:
        confidence = "medium"
    else:
        confidence = "low"

    if matching_attributes:
        explanation = f"Potential match based on {', '.join(matching_attributes[:3]).lower()}."
    else:
        explanation = "Possible partial overlap identified across item properties."

    return score, confidence, matching_attributes, differences, explanation


def _build_item_summary_for_ai(item: dict[str, Any]) -> str:
    """Format an item dictionary into a clean, safe summary for LLM prompt."""
    parts = [
        f"Name: {item.get('name', 'Unknown')}",
        f"Category: {item.get('ai_category') or item.get('category', 'Unknown')}",
        f"Location: {item.get('location', 'Unknown')}",
    ]
    if item.get("ai_primary_color"):
        parts.append(f"Color: {item.get('ai_primary_color')}")
    if item.get("ai_brand"):
        parts.append(f"Brand: {item.get('ai_brand')}")
    if item.get("ai_model"):
        parts.append(f"Model: {item.get('ai_model')}")
    if item.get("ai_distinctive_features"):
        features = item.get("ai_distinctive_features")
        if isinstance(features, list) and features:
            parts.append(f"Distinctive Features: {', '.join(features)}")
    if item.get("date_found"):
        parts.append(f"Date: {str(item.get('date_found'))[:10]}")
    return "\n".join(parts)


def evaluate_match_with_ai(
    target: dict[str, Any],
    candidate: dict[str, Any],
    base_score: int,
    base_confidence: str,
    base_matches: list[str],
    base_diffs: list[str],
    base_expl: str,
) -> dict[str, Any]:
    """Enhance match scoring with LLM semantic reasoning when configured, with safe fallback."""
    if not AIConfig.is_configured():
        return {
            "match_score": base_score,
            "confidence": base_confidence,
            "matching_attributes": base_matches,
            "differences": base_diffs,
            "explanation": base_expl,
        }

    prompt = f"""Compare these two campus lost & found item reports and determine if they could be the same object:

--- ITEM 1 (Reported Lost/Searched) ---
{_build_item_summary_for_ai(target)}

--- ITEM 2 (Reported in Inventory) ---
{_build_item_summary_for_ai(candidate)}

Evaluate the potential match and return strict JSON."""

    try:
        client = get_ai_client(require_configured=True)
        result = client.generate_json(
            prompt=prompt, system_instruction=MATCHING_SYSTEM_INSTRUCTION
        )
        if isinstance(result, dict):
            raw_score = result.get("match_score")
            try:
                score = max(0, min(100, int(raw_score)))
            except (TypeError, ValueError):
                score = base_score

            conf = str(result.get("confidence") or "").lower()
            if conf not in ("high", "medium", "low"):
                conf = "high" if score >= 80 else ("medium" if score >= 60 else "low")

            matches = result.get("matching_attributes")
            if not isinstance(matches, list) or not matches:
                matches = base_matches

            diffs = result.get("differences")
            if not isinstance(diffs, list):
                diffs = base_diffs

            expl = str(result.get("explanation") or base_expl).strip()

            return {
                "match_score": score,
                "confidence": conf,
                "matching_attributes": matches,
                "differences": diffs,
                "explanation": expl,
            }
    except AIError as exc:
        logger.warning(f"AI semantic match failed ({exc}), falling back to deterministic score.")
    except Exception as exc:
        logger.warning(f"AI matching error ({exc}), using deterministic fallback.")

    return {
        "match_score": base_score,
        "confidence": base_confidence,
        "matching_attributes": base_matches,
        "differences": base_diffs,
        "explanation": base_expl,
    }


def find_potential_matches(
    lost_item_data: dict[str, Any],
    candidate_items: list[dict[str, Any]],
    top_n: int = 5,
) -> dict[str, Any]:
    """Retrieve and rank candidate matches for a target item.

    1. Coarse deterministic evaluation of candidate pool
    2. Filters promising candidates (score >= 35)
    3. Executes AI semantic refinement on top candidates
    4. Ranks and returns structured potential matches
    """
    if not lost_item_data:
        return format_ai_response(False, error="Target item data is required.")

    if not candidate_items:
        return format_ai_response(
            True,
            data={
                "target_item_id": lost_item_data.get("id"),
                "total_candidates_checked": 0,
                "matches": [],
            },
        )

    evaluated_candidates = []

    # Step 1: Deterministic pre-scoring for candidate filtering
    for cand in candidate_items:
        # Don't match item with itself
        if cand.get("id") and lost_item_data.get("id") and cand.get("id") == lost_item_data.get("id"):
            continue

        score, conf, matches, diffs, expl = compute_deterministic_match_score(
            lost_item_data, cand
        )

        # Retain candidate if baseline score meets threshold (>= 35)
        if score >= 35:
            evaluated_candidates.append(
                {
                    "candidate": cand,
                    "base_score": score,
                    "base_conf": conf,
                    "base_matches": matches,
                    "base_diffs": diffs,
                    "base_expl": expl,
                }
            )

    # Sort descending by preliminary score
    evaluated_candidates.sort(key=lambda x: x["base_score"], reverse=True)
    top_candidates = evaluated_candidates[:top_n]

    results = []
    # Step 2: Semantic AI evaluation on top candidates
    for item_eval in top_candidates:
        cand = item_eval["candidate"]
        refined = evaluate_match_with_ai(
            target=lost_item_data,
            candidate=cand,
            base_score=item_eval["base_score"],
            base_confidence=item_eval["base_conf"],
            base_matches=item_eval["base_matches"],
            base_diffs=item_eval["base_diffs"],
            base_expl=item_eval["base_expl"],
        )

        results.append(
            {
                "candidate_id": cand.get("id"),
                "candidate_name": cand.get("name"),
                "candidate_category": cand.get("category"),
                "candidate_location": cand.get("location"),
                "candidate_image": cand.get("image_data") or cand.get("image_url"),
                "candidate_status": cand.get("status", "Available"),
                "match_score": refined["match_score"],
                "confidence": refined["confidence"],
                "matching_attributes": refined["matching_attributes"],
                "differences": refined["differences"],
                "explanation": refined["explanation"],
            }
        )

    # Final sort by match score
    results.sort(key=lambda x: x["match_score"], reverse=True)

    return format_ai_response(
        True,
        data={
            "target_item_id": lost_item_data.get("id"),
            "total_candidates_checked": len(candidate_items),
            "matches": results,
        },
    )
