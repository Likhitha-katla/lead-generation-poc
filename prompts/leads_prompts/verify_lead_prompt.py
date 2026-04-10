"""
Prompt builder for verifying a single organization lead against our ICP.
This file lives in prompts and exposes a builder function to keep prompts
outside application logic.
"""
import json
import os
from typing import Dict, Any


def _load_hexa() -> str:
    try:
        path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "hexa.json"))
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Include the full business profile and buyer persona for richer comparison.
        selected_icp = data.get("selected_icp") or {}
        full_profile = {
            "business_profile": data.get("profile") or {},
            "selected_icp": {
                "segment_brief": selected_icp.get("segment_brief"),
                "persona_brief": selected_icp.get("persona_brief"),
                # "buyer_persona": selected_icp.get("buyer_persona") or {},
                "company_profile": selected_icp.get("company_profile") or {},
            },
        }

        return json.dumps(full_profile, indent=2)
    except Exception:
        return "{}"


def build_verify_lead_prompt(lead: Dict[str, Any]) -> str:
    """Build a prompt instructing the model to search the web (Google)
    for the lead's website and LinkedIn, then compare the findings to our
    full profile and buyer persona and return a compact JSON verdict.

    Expected output JSON:
    {
      "qualified": true|false,
      "score": 0-100,
      "reasons": ["..."],
      "source_urls": ["https://...", "https://linkedin.com/..."]
    }
    """

    hexa = _load_hexa()

    # Expect a minimal lead dict. Only use these fields to keep the prompt small.
    name = lead.get("name") or lead.get("company") or "Unknown Company"
    linkedin = lead.get("linkedin_url") or lead.get("linkedin") or ""
    website = lead.get("website_url") or lead.get("validated_domain") or lead.get("website") or ""
    industry = lead.get("industry") or ""
    estimated_employees = lead.get("estimated_employees") or lead.get("estimated_num_employees") or ""
    revenue = lead.get("revenue") or lead.get("parsed_revenue") or ""

    prompt = f"""
You are an assistant that can search the web via Google Search tool.

Context - Our full profile and buyer persona (Hexa reference):
{hexa}

Lead to verify (minimal):
Name: {name}
Website: {website}
LinkedIn: {linkedin}
Industry: {industry}
Estimated employees: {estimated_employees}
Revenue: {revenue}

Task:
1) Use Google Search and visit the company's website and LinkedIn (if available).
2) Determine whether this organization matches our full profile and buyer persona above, focusing on:
   - industry fit
   - company size and employee count
   - revenue band
   - match to the buyer persona's responsibilities, pain points, and decision-making context
   - presence of essential tools and tech signals
3) Return ONLY valid JSON with keys: "qualified" (boolean), "score" (0-100 int),
   "reasons" (array of short strings), and "source_urls" (array of urls you used).

Notes:
- Be concise in reasons (1-3 short bullets).
- If uncertain, set "qualified" to false and explain why.
- Do NOT include any extra commentary outside the JSON.

Required JSON structure (respond exactly in this format):
{{
    "qualified": true,
    "score": 85,
    "reasons": ["industry match", "company size within target"],
    "source_urls": ["https://example.com", "https://linkedin.com/..."]
}}

Return only the JSON object above. Do not add surrounding text or explanation.
"""

    return prompt
