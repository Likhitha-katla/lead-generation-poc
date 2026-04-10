from typing import List


PROMPT_TEMPLATE = """
You are generating Apollo.io organization filters.

Read the segment carefully and choose the MOST relevant industries.

RULES FOR INDUSTRY:
- Select ONLY from the allowed industry list provided below.
- Return 2 industries that are the best fit for the segment.
- Use exact lowercase spelling.
- Do not modify wording.
- Do not invent new industries.

Segment description:
__SEGMENT_BRIEF_DESCRIPTION__

Allowed industries:
accounting, agriculture, airlines/aviation, alternative dispute resolution,
alternative medicine, animation, apparel & fashion, architecture & planning,
arts & crafts, automotive, aviation & aerospace, banking, biotechnology,
broadcast media, building materials, business supplies & equipment,
capital markets, chemicals, civic & social organization, civil engineering,
commercial real estate, computer & network security, computer games,
computer hardware, computer networking, computer software, construction,
consumer electronics, consumer goods, consumer services, cosmetics, dairy,
defense & space, design, e-learning, education management,
electrical/electronic manufacturing, entertainment, environmental services,
events services, executive office, facilities services, farming,
financial services, fine art, fishery, food & beverages, food production,
fund-raising, furniture, gambling & casinos, glass, ceramics & concrete,
government administration, government relations, graphic design,
health, wellness & fitness, higher education, hospital & health care,
hospitality, human resources, import & export, individual & family services,
industrial automation, information services,
information technology & services, insurance, international affairs,
international trade & development, internet, investment banking,
investment management, judiciary, law enforcement, law practice,
legal services, legislative office, leisure, travel & tourism,
libraries, logistics & supply chain, luxury goods & jewelry, machinery,
management consulting, maritime, market research,
marketing & advertising, mechanical or industrial engineering,
media production, medical devices, medical practice,
mental health care, military, mining & metals,
motion pictures & film, museums & institutions, music,
nanotechnology, newspapers, nonprofit organization management,
oil & energy, online media, outsourcing/offshoring,
package/freight delivery, packaging & containers,
paper & forest products, performing arts, pharmaceuticals,
philanthropy, photography, plastics, political organization,
primary/secondary education, printing,
professional training & coaching, program development,
public policy, public relations & communications,
public safety, publishing, railroad manufacture,
ranching, real estate, recreational facilities & services,
religious institutions, renewables & environment, research,
restaurants, retail, security & investigations,
semiconductors, shipbuilding, sporting goods, sports,
staffing & recruiting, supermarkets, telecommunications,
textiles, think tanks, tobacco, translation & localization,
transportation/trucking/railroad, utilities,
venture capital & private equity, veterinary,
warehousing, wholesale, wine & spirits,
wireless, writing & editing

Allowed industries are above. Annual Revenue (raw input from user):
__ANNUAL_REVENUE__

Now generate keywords.

RULES FOR KEYWORDS (APOLLO-STYLE — CRITICAL):

- Generate 25–40 short, realistic Apollo-style keywords.
- Keywords must resemble topical tags used for targeting.
- Use short phrases (1–4 words max).
- No long descriptive sentences.
- No marketing language.
- No quotation marks inside output.
- Do NOT explain anything.

STRUCTURE GUIDELINES:

1. Include industry category terms
   Example:
   information technology & services
   marketing & advertising
   computer software
   internet

2. Include solution-category keywords
   Example:
   augmented reality
   virtual reality
   3d visualization
   immersive experiences
   enterprise software
   digital transformation

3. Include enterprise intent terms
   Example:
   enterprise buyers
   digital workplace
   innovation strategy
   technology adoption
   customer experience

4. Include tool ecosystem keywords (from essential_tools list)
   Convert tools into clean searchable tags.
   Example:
   adobe experience cloud
   salesforce marketing cloud
   google analytics
   microsoft power bi
   jira
   slack
   tableau
   zoom
   vimeo enterprise

5. Include buyer-role or org-level targeting terms
   Example:
   cmo
   marketing leadership
   enterprise marketing
   b2b
   enterprise applications

FORMAT RULES:
- Return keywords as ONE comma-separated string.
- Do NOT return JSON array.
- Do NOT add extra commentary.
- All lowercase.
- Avoid repeating similar phrases.
- Keep realistic and searchable.

Example output style:

information technology & services, marketing & advertising, computer software, augmented reality, virtual reality, immersive experiences, enterprise software, digital transformation, adobe experience cloud, salesforce marketing cloud, google analytics, tableau, jira, slack, cmo, enterprise marketing, b2b, enterprise buyers, customer experience, digital workplace

Enterprise tools:
__ESSENTIAL_TOOLS__

Example keyword style:
"interactive 3d product visualization, enterprise ar platform, immersive digital experience, adobe experience cloud integration"

----------------------------------------
REVENUE RULES (CRITICAL):
- Convert the annual revenue into numeric values.
- DO NOT return 5K, 2M, 3B etc.
- MUST return full integers like:
  5000
  2000000
  3000000000
- Extract revenue_min and revenue_max from the provided revenue text.
- If revenue is "5M to 50M", return:
  revenue_min = 5000000
  revenue_max = 50000000

Return ONLY this JSON format:

{
  "organization_industries": [],
  "organization_num_employees_ranges": [],
  "organization_locations": [],
  "revenue_min": 0,
  "revenue_max": 0,
  "q_keywords": ""
}
"""


def build_icp_to_apollo_prompt(
    segment_brief_description: str,
    essential_tools: List[str],
    annual_revenue: str,
    geography: str,
) -> str:
    essential_tools_text = ", ".join(essential_tools or [])
    return (
        PROMPT_TEMPLATE
        .replace("__SEGMENT_BRIEF_DESCRIPTION__", segment_brief_description or "")
        .replace("__ESSENTIAL_TOOLS__", essential_tools_text)
        .replace("__ANNUAL_REVENUE__", annual_revenue or "")
    )
