# # prompts/leads_prompts/verify_lead_prompt.py
# import json
# import os
# from typing import Dict, Any


# def _load_hexa() -> str:
#     try:
#         path = os.path.abspath(
#             os.path.join(os.path.dirname(__file__), "..", "..", "hexa.json")
#         )

#         with open(path, "r", encoding="utf-8") as f:
#             data = json.load(f)

#         selected_icp = data.get("selected_icp") or {}
#         profile = data.get("profile") or {}
#         company_profile = selected_icp.get("company_profile") or {}
#         buyer_persona = selected_icp.get("buyer_persona") or {}

#         full_profile = {
#             "business_summary": {
#                 "description": profile.get("description_of_my_business"),
#                 "industry": profile.get("industry"),
#                 "how_it_stands_out": profile.get("how_it_stands_out"),
#                 "key_capabilities": [
#                     item.get("title")
#                     for item in profile.get("key_capabilities", [])
#                     if isinstance(item, dict) and item.get("title")
#                 ],
#             },
#             "selected_icp": {
#                 "segment_brief": selected_icp.get("segment_brief"),
#                 "persona_brief": selected_icp.get("persona_brief"),
#                 "buyer_persona": {
#                     "responsibilities_and_kpis": buyer_persona.get("responsibilities_and_kpis", []),
#                     "buying_committee_role": buyer_persona.get("buying_committee_role", []),
#                     "decision_making_process": buyer_persona.get("decision_making_process", []),
#                     "beliefs": buyer_persona.get("beliefs", []),
#                     "top_motivations": buyer_persona.get("motivations", {}).get("real_motivation", []),
#                 },
#                 "company_profile": {
#                     "company_type": company_profile.get("company_type"),
#                     "company_size": company_profile.get("company_size"),
#                     "annual_revenue": company_profile.get("annual_revenue"),
#                     "geographic_location": company_profile.get("geographic_location"),
#                 },
#             },
#         }

#         return json.dumps(full_profile, indent=2)

#     except Exception:
#         return "{}"


# def build_verify_lead_prompt(lead: Dict[str, Any]) -> str:
#     hexa = _load_hexa()

#     name = lead.get("name") or lead.get("company") or "Unknown Company"
#     linkedin = lead.get("linkedin_url") or lead.get("linkedin") or ""
#     website = (
#         lead.get("website_url")
#         or lead.get("validated_domain")
#         or lead.get("website")
#         or ""
#     )
#     industry = lead.get("industry") or ""
#     estimated_employees = (
#         lead.get("estimated_employees")
#         or lead.get("estimated_num_employees")
#         or ""
#     )
#     revenue = lead.get("revenue") or lead.get("parsed_revenue") or ""

#     prompt = f"""
# You are an expert B2B lead qualification and outreach intelligence assistant.

# Use the lead data provided below, including the company website, LinkedIn URL, Apollo-fetched fields, and your general B2B knowledge.

# Your job is to independently perform the following 3 tasks for the given company.

# IMPORTANT:
# - All 3 tasks are completely independent.
# - Do NOT mix outputs from one task into another.
# - Perform all tasks in a single response.
# - Return ONLY valid JSON.
# - No explanations outside JSON.

# ==================================================
# OUR ICP + BUYER PERSONA CONTEXT
# ==================================================
# {hexa}

# ==================================================
# COMPANY TO VERIFY
# ==================================================
# Company Name: {name}
# Website: {website}
# LinkedIn: {linkedin}
# Industry: {industry}
# Estimated Employees: {estimated_employees}
# Revenue: {revenue}

# ==================================================
# TASK 1 → ICP MATCH ANALYSIS
# ==================================================
# Compare this company with our ICP using:
# - company website
# - Apollo fetched data
# - LinkedIn URL from the lead

# Strongly evaluate:
# - industry alignment
# - company size fit
# - revenue fit
# - technology/tool signals
# - service fit
# - decision-maker relevance
# - business maturity
# - need fit

# Return:
# - matched (true/false)
# - score out of 100
# - strong business reasons

# ==================================================
# TASK 2 → CONTACT DISCOVERY
# ==================================================
# Based on our buyer persona, find the BEST people in this company whom we can contact for project discussions.

# Focus on finding:
# - founders
# - CEOs
# - CTOs
# - VP / Director level people
# - Heads of AI / Engineering / Product / Innovation
# - decision makers
# - budget holders
# - project owners

# Find PUBLIC LinkedIn URLs only if you can confidently infer them from the provided lead data.

# Only return highly relevant contacts.

# ==================================================
# TASK 3 → TOP 3 BUSINESS PAIN POINTS
# ==================================================
# Analyze the company and identify the TOP 3 business pain points that can be used for manual cold outreach email.

# Pain points must be:
# - business specific
# - realistic
# - high value
# - directly useful for outreach
# - service/opportunity focused

# Examples:
# - slow lead qualification
# - manual workflows
# - poor automation
# - scaling issues
# - inefficient customer support
# - data silos
# - AI adoption gap

# ==================================================
# RETURN FORMAT (STRICT JSON ONLY)
# ==================================================
# STRICT RULE:
# Return only JSON object.
# Do not add markdown.
# Do not add explanation.
# Do not add text before or after JSON.

# {{
#     "icp_match": {{
#         "matched": true,
#         "score": 90,
#         "reasons": [
#             "Strong industry alignment",
#             "Company size fits target ICP",
#             "Technology maturity matches our offering"
#         ],
#         "source_urls": []
#     }},
#     "contacts": [
#         {{
#             "name": "John Doe",
#             "title": "CTO",
#             "linkedin_url": "https://linkedin.com/in/johndoe",
#             "reason": "Primary technical decision maker"
#         }}
#     ],
#     "pain_points": [
#         "Manual business workflows",
#         "Poor lead qualification efficiency",
#         "Scaling sales operations"
#     ],
#     "source_urls": []
# }}


# """

#     return prompt
