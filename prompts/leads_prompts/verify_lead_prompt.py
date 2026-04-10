# prompts/leads_prompts/verify_lead_prompt.py
import json
import os
from typing import Dict, Any


def _load_hexa() -> str:
    try:
        path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "hexa.json")
        )

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        selected_icp = data.get("selected_icp") or {}
        profile = data.get("profile") or {}
        company_profile = selected_icp.get("company_profile") or {}
        buyer_persona = selected_icp.get("buyer_persona") or {}

        full_profile = {
            "business_summary": {
                "description": profile.get("description_of_my_business"),
                "industry": profile.get("industry"),
                "how_it_stands_out": profile.get("how_it_stands_out"),
                "key_capabilities": [
                    item.get("title")
                    for item in profile.get("key_capabilities", [])
                    if isinstance(item, dict) and item.get("title")
                ],
            },
            "selected_icp": {
                "segment_brief": selected_icp.get("segment_brief"),
                "persona_brief": selected_icp.get("persona_brief"),
                "buyer_persona": {
                    "responsibilities_and_kpis": buyer_persona.get("responsibilities_and_kpis", []),
                    "buying_committee_role": buyer_persona.get("buying_committee_role", []),
                    "decision_making_process": buyer_persona.get("decision_making_process", []),
                    "beliefs": buyer_persona.get("beliefs", []),
                    "top_motivations": buyer_persona.get("motivations", {}).get("real_motivation", []),
                },
                "company_profile": {
                    "company_type": company_profile.get("company_type"),
                    "company_size": company_profile.get("company_size"),
                    "annual_revenue": company_profile.get("annual_revenue"),
                    "geographic_location": company_profile.get("geographic_location"),
                },
            },
        }

        return json.dumps(full_profile, indent=2)

    except Exception:
        return "{}"


def build_verify_lead_prompt(lead: Dict[str, Any]) -> str:
    hexa = _load_hexa()

    name = lead.get("name") or lead.get("company") or "Unknown Company"
    linkedin = lead.get("linkedin_url") or lead.get("linkedin") or ""
    website = (
        lead.get("website_url")
        or lead.get("validated_domain")
        or lead.get("website")
        or ""
    )
    industry = lead.get("industry") or ""
    estimated_employees = (
        lead.get("estimated_employees")
        or lead.get("estimated_num_employees")
        or ""
    )
    revenue = lead.get("revenue") or lead.get("parsed_revenue") or ""


    prompt = f"""
You are an expert B2B lead intelligence, ICP qualification, and outbound research assistant.

Your task is to deeply analyze the company using:
1. Apollo structured lead data
2. ICP + buyer persona context
3. Google search and public web research

Your output will be used directly for sales outreach and lead qualification.

==================================================
MANDATORY WEB RESEARCH INSTRUCTION
==================================================
Do NOT rely only on Apollo input data.

Apollo data is only the base input.

You MUST use Google search and public web sources to research the company before generating the response.

Search the web for:
- official company website
- LinkedIn company page
- leadership / about pages
- recent news / press releases
- funding / acquisitions / expansion updates
- hiring signals / careers page
- product / service offerings
- AI / digital transformation initiatives
- operational pain signals
- leadership LinkedIn profiles
- decision-maker public profiles

Always validate and enrich Apollo data using web research.

If web findings contradict Apollo data, prioritize the latest reliable public source.

IMPORTANT:
Focus on finding REAL decision-makers and REAL business pain.

==================================================
OUTPUT STYLE
==================================================
- sharp
- executive
- sales-intelligence focused
- point-to-point
- business-impact driven
- no fluff
- no unnecessary explanation
- concise and professional

VOICE TONE:
Use an executive sales intelligence tone:
clear, confident, concise, insight-driven, and business-focused.

==================================================
STRICT RULES
==================================================
- Return ONLY valid JSON
- No markdown
- No explanation outside JSON
- No fabricated people
- No fake LinkedIn URLs
- No hallucinated company facts
- If data confidence is low, return fewer contacts instead of inventing
- Every reason must be one-line and business focused

==================================================
ICP + BUYER CONTEXT
==================================================
{hexa}

==================================================
COMPANY DETAILS
==================================================
- Company Name: {name}
- Website: {website}
- LinkedIn: {linkedin}
- Industry: {industry}
- Estimated Employees: {estimated_employees}
- Revenue: {revenue}

==================================================
RETURN EXACTLY ONE JSON OBJECT
==================================================
Fields:
1. icp_match
2. contacts
3. pain_points
4. source_urls

==================================================
1) ICP MATCH ANALYSIS
==================================================
Determine whether this company is a strong ICP fit.

Return:
- matched: true or false
- score: integer from 0 to 100
- reason: exactly one sharp line
- brief_explanation: 2 to 3 short business reasons

Focus on:
- industry alignment
- company size
- maturity / revenue fit
- geography fit
- buyer persona relevance
- business need alignment
- solution pain fit

Make the explanation short and decision-focused.

Good example:
"Strong ICP fit due to company scale, decision-maker alignment, and visible automation pain"

==================================================
2) CONTACTS (VERY IMPORTANT)
==================================================
Identify 3 to 4 HIGH-CONFIDENCE stakeholders who are most likely to influence or approve a buying decision for this company.

Do NOT use fixed titles.

Instead, determine the most relevant people to contact based on:
- company industry
- company business model
- department likely facing the pain
- solution relevance
- budget ownership
- operational ownership
- strategic decision-making influence

Choose stakeholders dynamically based on who would realistically:
- feel the business pain
- own the workflow/problem area
- influence vendor evaluation
- approve budget
- make the final decision

For each contact return:
- name
- title
- linkedin_url
- reason

Reason must be exactly ONE sharp business line.

Examples:
- "Owns the workflow currently affected by operational inefficiencies"
- "Likely budget approver for AI and automation initiatives"
- "Directly responsible for solving this business problem"

IMPORTANT:
- Use only real publicly available LinkedIn URLs
- Do NOT fabricate people
- If confidence is low, return fewer contacts
- Focus only on the most relevant decision-makers for THIS company

==================================================
3) PAIN POINTS (MOST IMPORTANT)
==================================================
You are a B2B Sales Intelligence Researcher.
Your goal is to find REAL, SPECIFIC insights about the company and the lead.

CRITICAL INSTRUCTIONS:
1. Use Google Search to find at least 3-5 sources about the company.
2. Search for:
   - Company website pages like About, Services, Case Studies, Blog
   - Recent news articles or press releases
   - LinkedIn company page updates
   - Industry reports mentioning the company
   - Customer reviews or testimonials
   - Job postings that reveal internal challenges
   - Competitor comparisons

EVIDENCE-BASED PAIN POINTS ONLY:
- Quote specific facts you found.
- Reference actual initiatives, job postings, or public statements.
- Use real challenges supported by evidence.
- Do NOT make assumptions without evidence.

YOUR RESEARCH PROCESS:
STEP 1: Deep Research using Google Search
- "{name} services"
- "{name} news"
- "{name} challenges"
- "{name} hiring"
- "{name} jobs"
- "{name} LinkedIn"

STEP 2: Extract specific insights
- What they are currently working on
- What they are hiring for
- What customers or employees say about them
- Industry trends affecting them

STEP 3: Connect insights to pain points
- Match what you found to our value proposition
- Use their own language or terminology
- Reference specific timelines or events
- Give pain points in simple English, one line only
- Tell the pain point as a pain point, not in a generic manner

Return TOP 3 pain points only.

Examples:
- "Manual lead qualification is slowing sales velocity and wasting team time"
- "Fragmented workflows are driving higher operating cost and slower decisions"
- "Weak digital adoption is limiting productivity and customer response speed"

Pain points must sound like real, harsh business pain and must be directly usable in a cold email.

==================================================
4) SOURCE URLS
==================================================
Return maximum 5 public URLs used.

Prefer:
- official website
- LinkedIn company page
- leadership LinkedIn profiles
- news / funding articles
- press releases

==================================================
STRICT OUTPUT FORMAT
==================================================
{{
  "icp_match": {{
    "matched": true,
    "score": 88,
    "reason": "Strong ICP fit based on company scale and visible business pain",
    "brief_explanation": [
      "Industry strongly aligns with target segment",
      "Company maturity fits ideal customer profile",
      "Relevant decision-makers identified"
    ]
  }},
  "contacts": [
    {{
      "name": "John Doe",
      "title": "CTO",
      "linkedin_url": "https://www.linkedin.com/in/johndoe",
      "reason": "Owns technology roadmap and budget decisions"
    }}
  ],
  "pain_points": [
    "Manual workflows are slowing revenue-generating operations",
    "Operational inefficiencies are increasing internal costs",
    "Lack of intelligent automation reduces conversion efficiency"
  ],
  "source_urls": [
    "https://example.com"
  ]
}}

Return ONLY JSON.
"""
    return prompt
