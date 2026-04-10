# lead_verifier.py
import asyncio
import json
import hashlib
from pathlib import Path
import logging
import re
from typing import List, Dict, Any

from gemini_client import generate_with_retry
from prompts.leads_prompts.verify_lead_prompt import build_verify_lead_prompt

logger = logging.getLogger(__name__)


def _empty_verification(error_message: str = "") -> Dict[str, Any]:
    return {
        "icp_match": {
            "matched": False,
            "score": 0,
            "reasons": [error_message] if error_message else [],
            "source_urls": [],
        },
        "contacts": [],
        "pain_points": [],
        "source_urls": [],
        "raw": None,
    }


def _ensure_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _normalize_contact(contact: Any) -> Dict[str, Any]:
    if not isinstance(contact, dict):
        return {}

    return {
        "name": str(contact.get("name", "")).strip(),
        "title": str(contact.get("title", "")).strip(),
        "linkedin_url": str(contact.get("linkedin_url", "")).strip(),
        "reason": str(contact.get("reason", "")).strip(),
    }


def _extract_json_payload(raw: str) -> Any:
    if not raw:
        return None

    candidates = [raw]

    fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", raw, flags=re.DOTALL | re.IGNORECASE)
    candidates.extend(fenced)

    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(raw[start:end + 1])

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except Exception:
            continue

    return None


def _normalize_verification(data: Any) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return _empty_verification("AI output is not a JSON object")

    # Preferred shape from verify_lead_prompt.py
    if any(key in data for key in ("icp_match", "contacts", "pain_points", "source_urls")):
        icp_match = data.get("icp_match")
        contacts = data.get("contacts")
        pain_points = data.get("pain_points")
        source_urls = data.get("source_urls")
    else:
        icp_match = None
        contacts = None
        pain_points = None
        source_urls = None

    # Backward compatibility with the older nested shape
    if icp_match is None and any(key in data for key in ("segment_1", "segment_2", "segment_3")):
        segment_1 = data.get("segment_1") or {}
        segment_2 = data.get("segment_2") or {}
        segment_3 = data.get("segment_3") or {}

        icp_match = {
            "matched": segment_1.get("matched", False),
            "score": segment_1.get("score", 0),
            "reasons": segment_1.get("reasons", []),
            "source_urls": segment_1.get("source_urls", []),
        }
        contacts = segment_2.get("contacts", [])
        pain_points = segment_3.get("pain_points", [])
        source_urls = data.get("source_urls", [])

    if not isinstance(icp_match, dict):
        icp_match = {}

    raw_reasons = icp_match.get("reasons")
    if raw_reasons is None:
        raw_reasons = icp_match.get("reason")
    if raw_reasons is None:
        raw_reasons = icp_match.get("brief_explanation")

    raw_source_urls = icp_match.get("source_urls")
    if not raw_source_urls:
        raw_source_urls = data.get("source_urls", [])

    normalized_icp = {
        "matched": bool(icp_match.get("matched", False)),
        "score": int(icp_match.get("score", 0) or 0),
        "reasons": _ensure_list(raw_reasons),
        "brief_explanation": _ensure_list(icp_match.get("brief_explanation")),
        "source_urls": _ensure_list(raw_source_urls),
    }

    normalized_contacts = [_normalize_contact(item) for item in _ensure_list(contacts)]
    normalized_contacts = [item for item in normalized_contacts if item]

    normalized_pain_points = [
        str(item).strip()
        for item in _ensure_list(pain_points)
        if str(item).strip()
    ]

    normalized_source_urls = [
        str(item).strip()
        for item in _ensure_list(source_urls)
        if str(item).strip()
    ]

    return {
        "icp_match": normalized_icp,
        "contacts": normalized_contacts,
        "pain_points": normalized_pain_points,
        "source_urls": normalized_source_urls,
        "raw": data,
    }


def verify_leads(
    leads: List[Dict[str, Any]],
    max_leads: int = 20,
    timeout_per_call: int = 30,
    gemini_api_key: str = "",
) -> List[Dict[str, Any]]:
    """Verify top leads using Gemini (Google Search tool). Returns leads enriched with a `verification` field.

    - Only processes up to `max_leads` to limit cost/time.
    - Each verification attempts to parse JSON from the model.
    """
    checked = []

    for i, lead in enumerate(leads[:max_leads]):
        try:
            verification = None
            data = None

            # Create a minimal lead payload to send to the model to reduce tokens/costs
            minimal_lead = {
                "name": lead.get("name") or lead.get("company"),
                "website": lead.get("website_url") or lead.get("validated_domain"),
                "linkedin": lead.get("linkedin_url"),
                "industry": lead.get("industry") or lead.get("industries"),
                "estimated_employees": lead.get("estimated_num_employees") or lead.get("employee_count") or None,
                "revenue": lead.get("parsed_revenue") or lead.get("organization_revenue") or None,
            }

            prompt = build_verify_lead_prompt(minimal_lead)

            # Simple on-disk cache to avoid repeated LLM calls for same prompt
            cache_path = Path(".gemini_cache.json")
            cache = {}
            try:
                if cache_path.exists():
                    with cache_path.open("r", encoding="utf-8") as cf:
                        cache = json.load(cf)
            except Exception:
                cache = {}

            prompt_key = hashlib.sha256(prompt.encode("utf-8") if isinstance(prompt, str) else json.dumps(prompt).encode("utf-8")).hexdigest()
            cached_raw = cache.get(prompt_key)

            # For this verifier we prefer structured JSON output over tool
            # grounding, because the search-grounded path has been returning
            # empty tool responses in this SDK/runtime.
            expect_json_flag = True
            raw = asyncio.run(
                generate_with_retry(
                    prompt=prompt,
                    expect_json=expect_json_flag,
                    use_google_search=False,
                    api_key=gemini_api_key or None,
                )
            )

            # Coerce non-string outputs to string to avoid regex errors
            if raw is not None and not isinstance(raw, str):
                try:
                    raw = json.dumps(raw)
                except Exception:
                    raw = str(raw)

            # Save successful response to cache
            try:
                cache[prompt_key] = raw
                with cache_path.open("w", encoding="utf-8") as cf:
                    json.dump(cache, cf)
            except Exception:
                pass

            # If the client returns a JSON string, try parsing
            data = _extract_json_payload(raw)
            if data is None:
                # Try a lightweight heuristic fallback to provide useful output
                # when the LLM is unavailable or returns non-JSON.
                reason = f"Model returned non-JSON: {str(raw)[:300]}"
                verification = _heuristic_fallback_verification(minimal_lead, reason)

            if verification is None:
                verification = _normalize_verification(data)

        except Exception as e:
            logger.exception("Lead verification failed")
            # If we have a cached response, use it as a fallback
            if cached_raw:
                logger.warning("Using cached Gemini response due to error", extra={"lead_id": lead.get("id")})
                data = _extract_json_payload(cached_raw)
                if data is not None:
                    verification = _normalize_verification(data)
                else:
                    verification = _heuristic_fallback_verification(minimal_lead, f"Cached response not parseable: {str(e)[:200]}")
            else:
                verification = _empty_verification(str(e))

        lead = lead.copy()
        lead["verification"] = verification
        checked.append(lead)

    # Append any remaining leads without verification
    if len(leads) > max_leads:
        checked.extend(leads[max_leads:])

    return checked


def _heuristic_fallback_verification(lead: Dict[str, Any], reason: str) -> Dict[str, Any]:
    # Minimal deterministic fallback: mark as not matched but include
    # a helpful reason and preserve the raw model output for debugging.
    icp = {
        "matched": False,
        "score": 0,
        "reasons": ["Fallback applied: " + reason],
        "source_urls": [],
    }

    contacts = []
    pain_points = []

    return {
        "icp_match": icp,
        "contacts": contacts,
        "pain_points": pain_points,
        "source_urls": [],
        "raw": lead,
    }
