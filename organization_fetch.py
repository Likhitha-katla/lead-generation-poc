
from typing import Dict, Any, List, Tuple
from apollo_client import ApolloClient, ApolloAPIError
import socket
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class ApolloOrganisationLeadServiceError(Exception):
    pass


class ApolloOrganisationLeadService:

    def __init__(self, apollo_api_key: str):
        if not apollo_api_key:
            raise ApolloOrganisationLeadServiceError("Apollo API key is missing.")
        self.client = ApolloClient(api_key=apollo_api_key)

    def fetch_organisation_leads(
        self,
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:

        try:
            # Remove API key from payload
            payload = payload.copy()
            payload.pop("apollo_key", None)

            # Default pagination
            payload["page"] = 1
            payload["per_page"] = 10

            logger.info(f"Incoming payload: {payload}")

            # -------- INDUSTRY NORMALIZATION --------
            industries = payload.get("organization_industries")

            # Convert None → []
            if industries is None:
                industries = []

            # Convert string → list
            if isinstance(industries, str):
                industries = [industries]

            # Clean empty values
            industries = [i.strip() for i in industries if i and i.strip()]

            # Save back normalized version
            payload["organization_industries"] = industries

            all_qualified = []
            all_rejected = []
            all_deleted = []
            total_fetched = 0

            # MULTIPLE INDUSTRIES (Loop per industry)
            if industries:

                for industry in industries:
                    industry_payload = payload.copy()
                    industry_payload["organization_industries"] = [industry]

                    logger.info(f"Calling Apollo for industry: {industry}")

                    response = self.client.search_organizations(industry_payload)

                    if not isinstance(response, dict):
                        logger.warning(f"Invalid response for industry: {industry}")
                        continue

                    organisations = response.get("organizations", [])
                    total_fetched += len(organisations)

                    qualified, rejected, deleted = self.clean_and_filter(
                        organisations,
                        industry_payload
                    )

                    all_qualified.extend(qualified)
                    all_rejected.extend(rejected)
                    all_deleted.extend(deleted)

            # NO INDUSTRY PROVIDED (Single Call)
            else:
                logger.info("Calling Apollo without industry filter")

                response = self.client.search_organizations(payload)

                if isinstance(response, dict):
                    organisations = response.get("organizations", [])
                    total_fetched += len(organisations)

                    qualified, rejected, deleted = self.clean_and_filter(
                        organisations,
                        payload
                    )

                    all_qualified.extend(qualified)
                    all_rejected.extend(rejected)
                    all_deleted.extend(deleted)

            # REMOVE DUPLICATES (by validated domain)
            unique_qualified = {}
            for org in all_qualified:
                domain = org.get("validated_domain")
                if domain:
                    unique_qualified[domain] = org

            final_qualified = list(unique_qualified.values())

            logger.info(
                f"Fetch completed | Total: {total_fetched}, "
                f"Qualified: {len(final_qualified)}, "
                f"Rejected: {len(all_rejected)}, "
                f"Deleted: {len(all_deleted)}"
            )

            return {
                "total_fetched": total_fetched,
                "qualified": len(final_qualified),
                "rejected": len(all_rejected),
                "deleted": len(all_deleted),
                "leads": final_qualified
            }

        except ApolloAPIError as e:
            logger.error(f"Apollo API error: {str(e)}")
            raise ApolloOrganisationLeadServiceError(str(e))

        except Exception as e:
            logger.exception("Unexpected error during organization lead fetch.")
            raise ApolloOrganisationLeadServiceError(
                f"Organisation lead fetch failed: {str(e)}"
            )



    # VALIDATION + FILTERING LOGIC
    def clean_and_filter(
        self,
        orgs: List[Dict[str, Any]],
        filters: Dict[str, Any]
    ) -> Tuple[List, List, List]:

        qualified = []
        rejected = []
        deleted = []

        employee_ranges = filters.get("organization_num_employees_ranges", [])
        organization_industries = filters.get("organization_industries", [])
        revenue_min = filters.get("revenue_min", 0)
        revenue_max = filters.get("revenue_max", 99999999999999)
        keyword_query = filters.get("q_keywords", "")

        for org in orgs:
            try:
                name = org.get("name", "Unknown")
                website = org.get("website_url")
                linkedin = org.get("linkedin_url")

                domain = self.extract_domain(org)

                # HARD DELETE CHECKS
                if not website and not linkedin:
                    deleted.append({"company": name, "reason": "No website & LinkedIn"})
                    continue

                if not domain:
                    deleted.append({"company": name, "reason": "Missing domain"})
                    continue

                if not self.dns_exists(domain):
                    deleted.append({"company": name, "reason": "Invalid domain"})
                    continue

                revenue = self.parse_revenue(org.get("organization_revenue"))

                if revenue is None:
                    deleted.append({"company": name, "reason": "Invalid revenue"})
                    continue

                # EMPLOYEE FILTER
                if employee_ranges and not self.employee_range_valid(
                    org.get("estimated_num_employees"), employee_ranges
                ):
                    rejected.append({"company": name, "reason": "Employee mismatch"})
                    continue

                # INDUSTRY FILTER
                org_industry = org.get("industry") or org.get("industries")

                if organization_industries and not self.organization_industry_valid(
                    org_industry,
                    organization_industries
                ):
                    rejected.append({"company": name, "reason": "Industry mismatch"})
                    continue

                # REVENUE FILTER
                if not (revenue_min <= revenue <= revenue_max):
                    rejected.append({"company": name, "reason": "Revenue mismatch"})
                    continue

                # KEYWORD FILTER
                score = self.keyword_score(org.get("keywords"), keyword_query)
                if score == 0:
                    rejected.append({"company": name, "reason": "Keyword mismatch"})
                    continue

                org["validated_domain"] = domain
                org["keyword_score"] = score
                org["parsed_revenue"] = revenue

                qualified.append(org)

            except Exception as e:
                logger.exception(f"Error processing organization: {org.get('name')}")
                deleted.append({
                    "company": org.get("name", "Unknown"),
                    "reason": f"Processing error: {str(e)}"
                })

        return qualified, rejected, deleted

    # ---------- UTILITIES ----------

    def extract_domain(self, org):
        try:
            website = org.get("website_url")
            if website:
                return urlparse(website).netloc.replace("www.", "")
        except Exception:
            pass
        return None

    def dns_exists(self, domain):
        try:
            socket.setdefaulttimeout(2)
            socket.gethostbyname(domain)
            return True
        except Exception:
            return False

    def parse_revenue(self, revenue):
        try:
            if revenue is None:
                return None
            return float(revenue)
        except (ValueError, TypeError):
            return None

    def employee_range_valid(self, emp, ranges):
        try:
            if emp is None:
                return False
            emp = int(emp)

            for r in ranges:
                if r.endswith("+"):
                    if emp >= int(r.replace("+", "")):
                        return True
                else:
                    low, high = map(int, r.split(","))
                    if low <= emp <= high:
                        return True
            return False
        except Exception:
            return False

    def organization_industry_valid(self, org_industries, allowed):
        try:
            if not org_industries or not allowed:
                return False

            # Normalize org industries to list
            if isinstance(org_industries, str):
                org_industries = [org_industries]

            org_industries = [i.lower().strip() for i in org_industries]
            allowed = [a.lower().strip() for a in allowed]

            return any(
                allowed_ind in org_ind
                for org_ind in org_industries
                for allowed_ind in allowed
            )

        except Exception:
            return False

    def keyword_score(self, org_keywords, query):
        try:
            if not org_keywords or not query:
                return 0

            terms = [
                q.strip().lower()
                for q in query.split(",")
                if q.strip()
            ]

            return sum(
                1 for k in org_keywords
                for t in terms if t in k.lower()
            )
        except Exception:
            return 0
        
