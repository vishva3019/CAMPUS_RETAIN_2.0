"""Campus Retain AI Assistant Service.

Provides an intelligent, grounded conversational assistant for students to:
- Find lost and found inventory items using natural language
- Learn how the platform, claiming, and reporting workflows operate
- Follow up on details without hallucinating fake records or leaking secrets.

CRITICAL RULES:
1. NEVER hallucinate or invent database entries.
2. Ground all item responses strictly in real database candidates from Phase 5 search.
3. Never expose secret verification details, auth credentials, or admin notes.
4. Assistant operates in advisory capacity only (cannot approve or reject claims).
5. 100% deterministic fallback when AI provider is offline.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import re
from typing import Any

from ai.client import format_ai_response, get_ai_client
from ai.config import AIConfig
from ai.exceptions import AIError
from ai.matching import _normalize_text, _tokenize
from ai.search import semantic_search

logger = logging.getLogger("campusretain.ai.assistant")

ASSISTANT_SYSTEM_INSTRUCTION = """You are Campus Retain AI, the intelligent campus lost-and-found assistant at Alliance University.
Your goal is to help students find lost items, understand claiming procedures, and navigate the platform.

CRITICAL GUIDELINES:
1. ZERO HALLUCINATION POLICY:
   - You must NEVER invent or assume database records exist.
   - Only reference items explicitly provided to you in the Grounded Candidate Records context.
   - If no candidate items are provided or matching, clearly state: "I couldn't find a relevant report in Campus Retain."
2. PRIVACY & SECURITY:
   - NEVER disclose secret verification details, passwords, tokens, or administrator remarks.
   - If asked for secret claim info, state that secret identifying details are strictly protected for anti-theft security.
3. ADVISORY ONLY:
   - You CANNOT approve or reject claims.
4. ACCURATE PLATFORM GUIDANCE:
   - Reporting Found: Fill the form, upload optional photo for AI vision analysis, and physically hand over the item to the DOSS office physical counter.
   - Reporting Lost: Fill the lost form; the AI matching engine automatically monitors opposing found reports in real time.
   - Claiming: Locate item in catalog, click 'Claim Property', enter Student ID and distinctive verification proof; submitted for administrator review.
5. CONCISE & FRIENDLY:
   - Keep answers under 3-4 sentences where possible, action-oriented and clear.
"""

PLATFORM_HELP_TOPICS: dict[str, str] = {
    "claim": """To claim an item on Campus Retain:
1. Locate the item in the catalog and click **Claim Property**.
2. Enter your Student ID, active phone number, and detailed ownership proof (e.g. unique scratches, stickers, or serial numbers).
3. Submit the claim — our AI assistant will perform a consistency assessment for the administrator.
4. An administrator at the DOSS office makes the final decision. Once approved, collect your item at the counter.""",

    "report_found": """To report a found item:
1. Click **Report Found** in the top navigation bar.
2. Enter item details and upload a photo — our Multimodal AI will automatically extract categories, colors, and brands.
3. Enter a secret identification detail (which remains hidden from the public).
4. **Important**: Bring the physical item to the DOSS office physical counter for secure custody.""",

    "report_lost": """To report a lost item:
1. Click **Report Lost** in the top navigation.
2. Describe what you lost, including category, last seen location, and distinctive features.
3. Submit the report — the AI matching engine will immediately compare your report against all existing and newly found items.""",

    "how_it_works": """Campus Retain AI is Alliance University's intelligent lost-and-found portal:
• **AI Vision**: Extracts structured colors, brands, and categories from photos.
• **Natural Language Search**: Type normal sentences like *"I lost my black Nike backpack near the library"*.
• **AI Match Discovery**: Automatically pairs lost reports with found items.
• **AI Claim Verification**: Evaluates ownership proof to assist administrators."""
}


def detect_user_intent(message: str) -> str:
    """Classifies user query intent using rule-based pattern matching."""
    norm = _normalize_text(message)

    # 1. Secret information probing
    if any(p in norm for p in ["secret detail", "secret answer", "admin password", "secret info", "tell me the secret", "secret of", "secret", "hack", "admin key"]):
        return "secret_inquiry"

    # 2. Claim guidance
    if any(p in norm for p in ["how to claim", "claim an item", "claim process", "how do i claim", "claiming work", "claim property", "how can i claim"]):
        return "claim_guidance"

    # 3. Report Found guidance
    if any(p in norm for p in ["report found", "report a found", "found something", "how to report found", "how do i report found", "how do i report a found", "hand over", "doss office"]):
        return "report_found_help"

    # 4. Report Lost guidance
    if any(p in norm for p in ["report lost", "report a lost", "how to report lost", "how do i report lost", "how do i report a lost", "register lost", "lost report"]):
        return "report_lost_help"

    # 5. Specific search queries
    if any(p in norm for p in ["lost", "found", "looking for", "find", "search", "anyone seen", "where is", "backpack", "phone", "bottle", "keys", "wallet", "calculator", "umbrella"]):
        return "search"

    # 6. General platform help
    if any(p in norm for p in ["how does this work", "how does campus retain work", "how it works", "what is campus retain", "features", "about campus retain", "platform help"]):
        return "platform_help"

    # Default general conversation
    return "conversation"


def sanitize_item_for_assistant(item: dict[str, Any]) -> dict[str, Any]:
    """Strips secret details, claimant contact info, and internal fields before passing to LLM."""
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "category": item.get("category"),
        "location": item.get("location"),
        "status": item.get("status", "Available"),
        "item_type": item.get("item_type", "found"),
        "ai_primary_color": item.get("ai_primary_color"),
        "ai_brand": item.get("ai_brand"),
        "relevance_score": item.get("relevance_score"),
        "relevance_label": item.get("relevance_label"),
    }


def handle_chat_interaction(
    message: str,
    items: list[dict[str, Any]],
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Processes student chat input, detects intent, searches database, and produces grounded response."""
    message = (message or "").strip()
    if not message:
        return format_ai_response(
            True,
            data={
                "message": "Hi! I'm Campus Retain AI. How can I help you find what you lost or use the platform today?",
                "intent": "greeting",
                "results": [],
                "suggested_actions": [
                    "🔎 Search found items",
                    "📝 How to report lost item",
                    "❓ How does claiming work?",
                ],
            },
        )

    intent = detect_user_intent(message)
    results: list[dict[str, Any]] = []

    # 1. Handle Secret Inquiry Refusal (Security guardrail)
    if intent == "secret_inquiry":
        return format_ai_response(
            True,
            data={
                "message": "For campus security and anti-theft privacy, secret verification details and administrative parameters cannot be disclosed. If this is your item, please submit a claim with your proof description for administrator review.",
                "intent": "security_refusal",
                "results": [],
                "suggested_actions": ["🔎 Search inventory", "❓ How does claiming work?"],
            },
        )

    # 2. Handle Claim Guidance
    if intent == "claim_guidance":
        return format_ai_response(
            True,
            data={
                "message": PLATFORM_HELP_TOPICS["claim"],
                "intent": "claim_guidance",
                "results": [],
                "suggested_actions": ["🔎 Search found items", "📝 Report a lost item"],
            },
        )

    # 3. Handle Report Found Help
    if intent == "report_found_help":
        return format_ai_response(
            True,
            data={
                "message": PLATFORM_HELP_TOPICS["report_found"],
                "intent": "report_found_help",
                "results": [],
                "suggested_actions": ["📝 Report Found item now", "🔎 View Inventory"],
            },
        )

    # 4. Handle Report Lost Help
    if intent == "report_lost_help":
        return format_ai_response(
            True,
            data={
                "message": PLATFORM_HELP_TOPICS["report_lost"],
                "intent": "report_lost_help",
                "results": [],
                "suggested_actions": ["📝 Report Lost item now", "🔎 Search found items"],
            },
        )

    # 5. Handle General Platform Help
    if intent == "platform_help":
        return format_ai_response(
            True,
            data={
                "message": PLATFORM_HELP_TOPICS["how_it_works"],
                "intent": "platform_help",
                "results": [],
                "suggested_actions": ["🔎 Search items", "📝 Report an item"],
            },
        )

    # 6. Search / Conversational Item Query Intent
    # Run Phase 5 semantic search over sanitized database records
    search_res = semantic_search(message, items, top_n=5)
    if search_res.get("success") and search_res.get("data"):
        raw_results = search_res["data"].get("results", [])
        # Only include results with reasonable relevance score (>= 40)
        results = [r for r in raw_results if r.get("relevance_score", 0) >= 40][:4]

    # If AI is configured, let LLM synthesize a concise grounded response
    if AIConfig.is_configured():
        sanitized_results = [sanitize_item_for_assistant(r) for r in results]
        prompt = f"""
Student Message: "{message}"

Grounded Candidate Records in Campus Retain (DO NOT invent items beyond this list):
{json.dumps(sanitized_results, indent=2)}

Provide a concise, helpful response (max 3 sentences) referencing any relevant items found. If none found, explain that no matching record exists and suggest providing more details (color, location, approximate date).
"""
        try:
            client = get_ai_client(require_configured=True)
            ai_reply = client.generate_text(
                prompt=prompt, system_instruction=ASSISTANT_SYSTEM_INSTRUCTION
            )
            if ai_reply and ai_reply.strip():
                return format_ai_response(
                    True,
                    data={
                        "message": ai_reply.strip(),
                        "intent": "search" if results else "no_results",
                        "results": results,
                        "suggested_actions": (
                            ["Claim this item", "Search another item"]
                            if results
                            else ["📝 Report Lost Item", "🔎 Try another search"]
                        ),
                    },
                )
        except AIError as exc:
            logger.warning(f"AI Assistant synthesis failed ({exc}), using deterministic response.")
        except Exception as exc:
            logger.warning(f"Unexpected Assistant error ({exc}), using deterministic response.")

    # 7. Deterministic Fallback Synthesis
    if results:
        top_item = results[0]
        top_name = top_item.get("name") or "Item"
        top_loc = top_item.get("location") or "Campus"
        msg = f"I found {len(results)} potentially relevant report{'s' if len(results) > 1 else ''} in the inventory! The top candidate is **{top_name}** at {top_loc} ({top_item.get('relevance_score', 80)}% Relevant). Would you like to review and claim it?"
    else:
        # Check if query was too vague (e.g. just "I lost my backpack" or "phone")
        tokens = _tokenize(message)
        if len(tokens) <= 2:
            msg = "I can help you search for your item! Could you tell me a few more details, such as the color, brand, or the campus location where you last saw it?"
        else:
            msg = "I couldn't find a matching report in Campus Retain for that description. Try specifying the item type, color, brand, or location — or report it as lost so the AI matching engine can alert you when it's found."

    return format_ai_response(
        True,
        data={
            "message": msg,
            "intent": "search" if results else "no_results",
            "results": results,
            "suggested_actions": (
                ["Claim this item", "Search again"]
                if results
                else ["📝 Report Lost Item", "❓ How does claiming work?"]
            ),
        },
    )
