
import json
import logging
import re
from typing import Dict, Any, List

from pydantic import BaseModel, ValidationError, Field

from gemini_client import generate_with_retry
from core.exceptions import APIError
from prompts.leads_prompts.icp_to_apollo_prompt import build_icp_to_apollo_prompt

logger = logging.getLogger(__name__)


# APOLLO RESPONSE SCHEMA MODEL
class ApolloFilterResponse(BaseModel):
    organization_industries: List[str] = Field(default_factory=list)
    organization_num_employees_ranges: List[str]
    organization_locations: List[str]  
    revenue_min: int
    revenue_max: int
    q_keywords: str


class ICPToApolloService:

    APOLLO_EMPLOYEE_BUCKETS = {
        "11,50": (11, 50),
        "51,200": (51, 200),
        "201,500": (201, 500),
        "501,1000": (501, 1000),
        "1001,5000": (1001, 5000),
        "5001,10000": (5001, 10000),
    }

    # EMPLOYEE RANGE NORMALIZATION
    @staticmethod
    def _normalize_employee_range(company_size: str) -> List[str]:

        if not company_size:
            raise APIError("invalid_company_size", "Company size is empty", 400)

        numbers = re.findall(r"\d+", company_size.replace(",", ""))

        if len(numbers) < 2:
            raise APIError(
                "invalid_company_size",
                "Unable to parse company size range",
                400
            )

        min_emp, max_emp = int(numbers[0]), int(numbers[1])

        if min_emp >= max_emp:
            raise APIError(
                "invalid_company_size",
                "Invalid employee range",
                400
            )

        ranges = []

        for bucket_key, (bucket_min, bucket_max) in ICPToApolloService.APOLLO_EMPLOYEE_BUCKETS.items():
            if not (max_emp < bucket_min or min_emp > bucket_max):
                ranges.append(bucket_key)

        if not ranges:
            raise APIError(
                "invalid_company_size",
                "Company size does not map to valid Apollo ranges",
                400
            )

        return ranges

    # AI OUTPUT VALIDATION 
    @staticmethod
    def _validate_ai_output(ai_data: Dict[str, Any]):

        if not isinstance(ai_data, dict):
            raise APIError("invalid_ai_response", "AI output is not JSON object", 500)

        organization_industries = ai_data.get("organization_industries", [])
        q_keywords = ai_data.get("q_keywords", "")
        revenue_min = ai_data.get("revenue_min")
        revenue_max = ai_data.get("revenue_max")

        if not isinstance(organization_industries, list):
            raise APIError("invalid_ai_response", "organization_industries must be list", 500)

        if not isinstance(q_keywords, str):
            raise APIError("invalid_ai_response", "q_keywords must be string", 500)

        try:
            revenue_min = int(revenue_min)
            revenue_max = int(revenue_max)
        except (TypeError, ValueError):
            raise APIError(
                "invalid_ai_response",
                "Revenue values must be numeric",
                500
            )

        if revenue_min >= revenue_max:
            raise APIError(
                "invalid_ai_response",
                "Revenue min must be less than max",
                500
            )

        organization_industries = [
            i.strip()
            for i in organization_industries
            if isinstance(i, str) and i.strip()
        ]

        return (
            organization_industries,
            q_keywords.strip(),
            revenue_min,
            revenue_max
        )

    # MAIN GENERATOR
    async def generate_apollo_filters(
        self,
        segment_brief_description: str,
        company_size: str,
        annual_revenue: str,
        geography: str,  
        essential_tools: List[str],
        gemini_api_key: str = "",
    ) -> Dict[str, Any]:

        if not segment_brief_description:
            raise APIError("missing_segment", "Segment description required", 400)

        if not geography:
            raise APIError("missing_geography", "Geography is required", 400)

        # Normalize employee range
        employee_ranges = self._normalize_employee_range(company_size)

        # Normalize geography directly 
        organization_locations = [
            loc.strip()
            for loc in re.split(r",|\n", geography)
            if loc.strip()
        ]

        prompt = build_icp_to_apollo_prompt(
            segment_brief_description=segment_brief_description,
            essential_tools=essential_tools,
            annual_revenue=annual_revenue,
            geography=geography
        )

        # Call Gemini
        try:
            ai_response = await generate_with_retry(
                prompt=prompt,
                expect_json=True,
                api_key=gemini_api_key or None,
            )
        except Exception as e:
            logger.exception("Gemini API failure")
            raise APIError("ai_generation_failed", str(e), 500)

        # Parse AI JSON
        try:
            ai_data = json.loads(ai_response)
        except Exception:
            logger.error("Invalid JSON from Gemini")
            raise APIError("invalid_ai_response", "AI did not return valid JSON", 500)

        # Validate AI output (without location)
        (
            industries,
            q_keywords,
            revenue_min,
            revenue_max
        ) = self._validate_ai_output(ai_data)

        # Construct final response
        try:
            response = ApolloFilterResponse(
                organization_industries=industries,
                organization_num_employees_ranges=employee_ranges,
                organization_locations=organization_locations,  
                revenue_min=revenue_min,
                revenue_max=revenue_max,
                q_keywords=q_keywords,
            )
        except ValidationError as e:
            logger.error("Response validation failed", extra={"error": str(e)})
            raise APIError(
                "response_validation_failed",
                "Invalid filter structure",
                500
            )

        return response.dict()
