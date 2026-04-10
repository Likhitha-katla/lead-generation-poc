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

        # Build a minimal ICP summary to keep prompts small and cost-effective
        minimal = {}
        sel = data.get("selected_icp") or {}
        company = sel.get("company_profile") or {}

        minimal["persona_brief"] = sel.get("persona_brief")
        minimal["company_profile"] = {
            "company_type": company.get("company_type"),
            "company_size": company.get("company_size"),
            "annual_revenue": company.get("annual_revenue")
        }

        return json.dumps(minimal, indent=2)
    except Exception:
        return "{}"


def build_verify_lead_prompt(lead: Dict[str, Any]) -> str:
    """Build a prompt instructing the model to search the web (Google)
    for the lead's website and LinkedIn, then compare the findings to our
    ICP (embedded) and return a compact JSON verdict.

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

Context — Our ICP (Hexa reference):
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
2) Determine whether this organization matches the ICP above focusing on:
   - industry fit
   - company size and employee count
   - revenue band
   - presence of essential tools and tech signals
3) Return ONLY valid JSON with keys: "qualified" (boolean), "score" (0-100 int),
   "reasons" (array of short strings), and "source_urls" (array of urls you used).

Notes:
- Be concise in reasons (1-3 short bullets).
- If uncertain, set "qualified" to false and explain why.
- Do NOT include any extra commentary outside the JSON.


        
Required JSON structure (respond exactly in this format):

Required JSON structure:
{{
    "qualified": true,
    "score": 85,
    "reasons": ["industry match", "company size within target"],
    "source_urls": ["https://example.com", "https://linkedin.com/..."]
}}

Return only the JSON object above. Do not add surrounding text or explanation.
"""
    
    return prompt 