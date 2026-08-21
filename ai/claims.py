"""AI Claim Verification Assistance Service.

Evaluates student claim proof descriptions against item metadata and verified characteristics
to provide structured confidence ratings, matching evidence, and discrepancy analysis
to help campus administrators make informed claim decisions.

CRITICAL SAFETY & PRIVACY RULES:
1. The AI is an assistant, NEVER the final decision maker. Recommendation is ALWAYS 'manual_review'.
2. The AI must NEVER automatically approve or reject claims.
3. Secret identification details and sensitive user credentials are never exposed publicly or logged.
4. Fallback deterministic verification ensures 100% uptime when AI providers are offline.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from typing import Any

from ai.client import format_ai_response, get_ai_client
from ai.config import AIConfig
from ai.exceptions import AIError
from ai.matching import (
    COLOR_FAMILIES,
    _are_colors_similar,
    _normalize_text,
    _tokenize,
)

logger = logging.getLogger("campusretain.ai.claims")

CLAIM_SYSTEM_INSTRUCTION = """You are Campus Retain AI's Claim Verification Assistant.
Your purpose is to assist campus administrators in assessing whether a student's submitted claim proof
is consistent with the known characteristics of a found/lost item.

CRITICAL RULES:
1. THE AI IS NOT A DECISION MAKER.
   - Recommendation MUST ALWAYS be "manual_review".
   - NEVER return "approve" or "reject".
   - NEVER state "This claim is definitely legitimate". Use neutral phrasing like "High-confidence match — administrator review recommended".
2. CONFIDENCE LEVELS:
   - 80-100: "high"
   - 60-79: "medium"
   - Below 60: "low"
3. HANDLING MISSING INFORMATION:
   - If the student did not mention a brand or color, that is NOT a conflicting factor (it is neutral).
   - Only flag explicit contradictions as conflicting factors (e.g. Item is Black, claimant states White; Item is Nike, claimant states Adidas).
4. PRIVACY:
   - Do NOT output sensitive passwords, tokens, or private phone numbers.
5. STRICT JSON OUTPUT adhering to schema:
{
  "confidence_score": <int 0-100>,
  "confidence_level": "<high | medium | low>",
  "matching_factors": ["<specific matching factor 1>", "<specific matching factor 2>"],
  "conflicting_factors": ["<specific conflict 1>"],
  "recommendation": "manual_review",
  "explanation": "<1-2 sentence neutral summary explaining consistency and why manual review is recommended>"
}
"""


def compute_deterministic_claim_score(
    claim_data: dict[str, Any], item_data: dict[str, Any]
) -> tuple[int, str, list[str], list[str], str]:
    """Computes a multi-factor deterministic baseline assessment of a claim proof against item data."""
    proof_text = _normalize_text(claim_data.get("proof_description") or "")
    proof_tokens = _tokenize(claim_data.get("proof_description") or "")

    item_name = item_data.get("name") or ""
    item_category = (item_data.get("ai_category") or item_data.get("category") or "").lower()
    item_color = (item_data.get("ai_primary_color") or "").lower()
    item_brand = (item_data.get("ai_brand") or "").lower()
    item_features = item_data.get("ai_distinctive_features") or []
    secret_detail = (item_data.get("secret_detail") or "").strip()

    matching_factors: list[str] = []
    conflicting_factors: list[str] = []
    base_score = 45  # Starting neutral baseline for submitted proof

    # 1. Secret detail check (up to 35 pts)
    if secret_detail:
        sec_norm = _normalize_text(secret_detail)
        sec_tokens = _tokenize(secret_detail)
        shared_sec_tokens = sec_tokens.intersection(proof_tokens)

        if sec_norm in proof_text or (sec_tokens and len(shared_sec_tokens) == len(sec_tokens)):
            base_score += 35
            matching_factors.append("Provided exact matching secret verification detail")
        elif len(shared_sec_tokens) >= max(1, len(sec_tokens) // 2):
            base_score += 25
            matching_factors.append("Provided partially matching secret verification attributes")
        elif len(proof_tokens) < 3:
            base_score -= 10
            conflicting_factors.append("Proof description does not corroborate recorded secret detail")
    else:
        base_score += 10  # No secret detail configured on item

    # 2. Category consistency (up to 15 pts)
    if item_category and item_category != "other":
        if item_category in proof_text or any(t in proof_tokens for t in item_category.split()):
            base_score += 15
            matching_factors.append(f"Category matches ({item_category.title()})")
        else:
            # Check for conflict
            pass

    # 3. Color consistency (up to 15 pts)
    if item_color and item_color != "unknown":
        mentioned_colors = [c for c in COLOR_FAMILIES.keys() if c in proof_tokens]
        if item_color in mentioned_colors:
            base_score += 15
            matching_factors.append(f"Color matches item ({item_color.title()})")
        elif any(_are_colors_similar(item_color, mc)[1] for mc in mentioned_colors):
            base_score += 10
            matching_factors.append(f"Similar color shade mentioned ({item_color.title()})")
        elif mentioned_colors:
            base_score -= 20
            conflicting_factors.append(
                f"Color conflict (Item recorded as {item_color.title()}, proof mentions {', '.join(mentioned_colors).title()})"
            )

    # 4. Brand consistency (up to 15 pts)
    if item_brand and item_brand != "null":
        if item_brand in proof_text:
            base_score += 15
            matching_factors.append(f"Brand confirmed in proof ({item_brand.title()})")
        else:
            # Check if claimant claimed a DIFFERENT known brand
            from ai.search import KNOWN_BRANDS
            other_brands = [b for b in KNOWN_BRANDS if b in proof_text and b != item_brand]
            if other_brands:
                base_score -= 25
                conflicting_factors.append(
                    f"Brand conflict (Item is {item_brand.title()}, proof mentions {', '.join(other_brands).title()})"
                )

    # 5. Distinctive visual features overlap (up to 15 pts)
    if isinstance(item_features, list) and item_features:
        feat_tokens = _tokenize(" ".join(item_features))
        shared_feat = feat_tokens.intersection(proof_tokens)
        if shared_feat:
            base_score += 15
            matching_factors.append(
                f"Distinctive visual characteristics confirmed: {', '.join(sorted(list(shared_feat))[:2])}"
            )

    # 6. Overall token overlap with item title/location
    item_tokens = _tokenize(f"{item_name} {item_data.get('location') or ''}")
    shared_item_tokens = item_tokens.intersection(proof_tokens)
    if shared_item_tokens:
        base_score += min(10, len(shared_item_tokens) * 3)

    # Bound score between 5 and 99 (never 100 to emphasize human review)
    final_score = max(10, min(96, base_score))

    if final_score >= 80 and not conflicting_factors:
        conf_level = "high"
        explanation = "The submitted claim proof is highly consistent with the item's verified characteristics. Administrator review recommended."
    elif final_score >= 60 and len(conflicting_factors) <= 1:
        conf_level = "medium"
        explanation = "The claim demonstrates moderate consistency with item attributes. Manual administrator inspection recommended."
    else:
        conf_level = "low"
        explanation = "The claim proof contains discrepancies or insufficient corroborating details. Careful administrator review recommended."

    if not matching_factors and final_score >= 40:
        matching_factors.append("General item description corroboration provided")

    return final_score, conf_level, matching_factors, conflicting_factors, explanation


def evaluate_claim_with_ai(
    claim_data: dict[str, Any],
    item_data: dict[str, Any],
    base_score: int,
    base_confidence: str,
    base_matches: list[str],
    base_conflicts: list[str],
    base_explanation: str,
) -> dict[str, Any]:
    """Uses LLM to perform deep semantic comparison of claim proof against item characteristics."""
    if not AIConfig.is_configured():
        return {
            "confidence_score": base_score,
            "confidence_level": base_confidence,
            "matching_factors": base_matches,
            "conflicting_factors": base_conflicts,
            "recommendation": "manual_review",
            "explanation": base_explanation,
        }

    # Prepare sanitized item payload (NEVER exposing secrets or raw passwords)
    sanitized_item = {
        "name": item_data.get("name"),
        "category": item_data.get("category"),
        "location": item_data.get("location"),
        "ai_category": item_data.get("ai_category"),
        "ai_primary_color": item_data.get("ai_primary_color"),
        "ai_brand": item_data.get("ai_brand"),
        "ai_distinctive_features": item_data.get("ai_distinctive_features") or [],
    }

    prompt = f"""
Item Verified Information:
{json.dumps(sanitized_item, indent=2)}

Student Submitted Proof Description:
"{claim_data.get('proof_description') or ''}"

Deterministic Baseline Pre-Assessment:
Score: {base_score} | Confidence: {base_confidence}
Baseline Matches: {json.dumps(base_matches)}
Baseline Conflicts: {json.dumps(base_conflicts)}

Analyze the claim consistency. Output structured JSON adhering to CLAIM_SYSTEM_INSTRUCTION.
"""

    try:
        client = get_ai_client(require_configured=True)
        result = client.generate_json(
            prompt=prompt, system_instruction=CLAIM_SYSTEM_INSTRUCTION
        )

        if isinstance(result, dict) and "confidence_score" in result:
            score = int(result.get("confidence_score") or base_score)
            score = max(5, min(98, score))

            conf = str(result.get("confidence_level") or base_confidence).lower()
            if conf not in ("high", "medium", "low"):
                conf = "high" if score >= 80 else ("medium" if score >= 60 else "low")

            matches = result.get("matching_factors")
            if not isinstance(matches, list) or not matches:
                matches = base_matches

            conflicts = result.get("conflicting_factors")
            if not isinstance(conflicts, list):
                conflicts = base_conflicts

            expl = str(result.get("explanation") or base_explanation).strip()

            return {
                "confidence_score": score,
                "confidence_level": conf,
                "matching_factors": matches,
                "conflicting_factors": conflicts,
                "recommendation": "manual_review",
                "explanation": expl,
            }
    except AIError as exc:
        logger.warning(f"AI claim evaluation failed ({exc}), using deterministic assessment.")
    except Exception as exc:
        logger.warning(f"Unexpected error in AI claim evaluation ({exc}), using deterministic assessment.")

    return {
        "confidence_score": base_score,
        "confidence_level": base_confidence,
        "matching_factors": base_matches,
        "conflicting_factors": base_conflicts,
        "recommendation": "manual_review",
        "explanation": base_explanation,
    }


def analyze_claim(
    claim_data: dict[str, Any], item_data: dict[str, Any]
) -> dict[str, Any]:
    """Main claim assessment entrypoint.

    Performs deterministic verification and optional LLM semantic analysis,
    returning structured assistance parameters for administrator review.
    """
    if not claim_data or not item_data:
        return format_ai_response(False, error="Claim data and item data are required for analysis.")

    # 1. Deterministic baseline evaluation
    (
        base_score,
        base_confidence,
        base_matches,
        base_conflicts,
        base_expl,
    ) = compute_deterministic_claim_score(claim_data, item_data)

    # 2. LLM deep semantic evaluation (or fallback)
    assessment = evaluate_claim_with_ai(
        claim_data=claim_data,
        item_data=item_data,
        base_score=base_score,
        base_confidence=base_confidence,
        base_matches=base_matches,
        base_conflicts=base_conflicts,
        base_explanation=base_expl,
    )

    return format_ai_response(
        True,
        data={
            "claim_id": claim_data.get("id"),
            "item_id": item_data.get("id"),
            "confidence_score": assessment["confidence_score"],
            "confidence_level": assessment["confidence_level"],
            "matching_factors": assessment["matching_factors"],
            "conflicting_factors": assessment["conflicting_factors"],
            "recommendation": "manual_review",
            "explanation": assessment["explanation"],
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
        },
    )
