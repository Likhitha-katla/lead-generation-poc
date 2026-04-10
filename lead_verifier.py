import asyncio
import json
import logging
from typing import List, Dict, Any

from gemini_client import generate_with_retry
from prompts.leads_prompts.verify_lead_prompt import build_verify_lead_prompt

logger = logging.getLogger(__name__)


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

            # Call the async Gemini wrapper synchronously
            # When using Google Search tool, Gemini may not support a JSON
            # response mime type together with tools. Request plain text and
            # extract JSON from the model output instead.
            raw = asyncio.run(
                generate_with_retry(
                    prompt=prompt,
                    expect_json=False,
                    use_google_search=True,
                    api_key=gemini_api_key or None,
                )
            )

            # If the client returns a JSON string, try parsing
            try:
                data = json.loads(raw)
            except Exception:
                # Fallback: try to extract a JSON block
                # naive extraction
                start = raw.find("{")
                end = raw.rfind("}")
                if start != -1 and end != -1 and end > start:
                    snippet = raw[start:end+1]
                    try:
                        data = json.loads(snippet)
                    except Exception:
                        data = {"qualified": False, "score": 0, "reasons": ["Model returned non-JSON"], "source_urls": []}
                else:
                    data = {"qualified": False, "score": 0, "reasons": ["No JSON returned"], "source_urls": []}

            # Normalize keys
            verification = {
                "qualified": bool(data.get("qualified", False)),
                "score": int(data.get("score", 0) or 0),
                "reasons": data.get("reasons", []) if isinstance(data.get("reasons", []), list) else [str(data.get("reasons"))],
                "source_urls": data.get("source_urls", []) if isinstance(data.get("source_urls", []), list) else [],
                "raw": data,
            }

        except Exception as e:
            logger.exception("Lead verification failed")
            verification = {"qualified": False, "score": 0, "reasons": [str(e)], "source_urls": [], "raw": None}

        lead = lead.copy()
        lead["verification"] = verification
        checked.append(lead)

    # Append any remaining leads without verification
    if len(leads) > max_leads:
        checked.extend(leads[max_leads:])

    return checked
