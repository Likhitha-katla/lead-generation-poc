
import time
import logging
import requests
from typing import Dict, Any

logger = logging.getLogger(__name__)

class ApolloAPIError(Exception):
    """Custom exception for Apollo API errors"""
    pass


class ApolloClient:

    BASE_URL = "https://api.apollo.io/api/v1/organizations/search"

    def __init__(
        self,
        api_key: str,
        timeout: int = 30,
        max_retries: int = 3,
        rate_limit_delay: float = 1.5
    ):
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.rate_limit_delay = rate_limit_delay

        self.headers = {
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "X-Api-Key": self.api_key
        }

    def search_organizations(
        self,
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:

        for attempt in range(1, self.max_retries + 1):

            try:
                logger.info(
                    "Apollo search attempt %s/%s",
                    attempt,
                    self.max_retries
                )

                response = requests.post(
                    self.BASE_URL,
                    headers=self.headers,
                    json=payload,
                    timeout=self.timeout
                )

                status_code = response.status_code

                # SUCCESS
                if status_code == 200:
                    logger.info("Apollo search successful")
                    return response.json()

                # RATE LIMIT
                elif status_code == 429:
                    wait = self.rate_limit_delay * attempt
                    logger.warning(
                        "Apollo rate limit hit. Retrying in %.2f sec. Attempt %s/%s",
                        wait,
                        attempt,
                        self.max_retries
                    )
                    time.sleep(wait)
                    continue

                # CLIENT ERRORS
                elif status_code in [400, 401, 403, 404]:

                    logger.error(
                        "Apollo client error %s: %s",
                        status_code,
                        response.text
                    )

                    raise ApolloAPIError(
                        f"Apollo Client Error {status_code}: {response.text}"
                    )

                # SERVER ERRORS
                elif 500 <= status_code < 600:
                    wait = 2 * attempt
                    logger.warning(
                        "Apollo server error %s. Retrying in %s sec. Attempt %s/%s",
                        status_code,
                        wait,
                        attempt,
                        self.max_retries
                    )

                    time.sleep(wait)
                    continue

                # UNKNOWN ERROR
                else:

                    logger.error(
                        "Unexpected Apollo response %s: %s",
                        status_code,
                        response.text
                    )

                    raise ApolloAPIError(
                        f"Unexpected Apollo response {status_code}: {response.text}"
                    )

            except requests.exceptions.Timeout:

                logger.warning(
                    "Apollo timeout on attempt %s/%s",
                    attempt,
                    self.max_retries
                )

                if attempt == self.max_retries:
                    logger.error("Apollo timeout after max retries")
                    raise ApolloAPIError("Apollo API timeout after retries")

                time.sleep(2 * attempt)

            except requests.exceptions.ConnectionError:

                logger.warning(
                    "Apollo connection error on attempt %s/%s",
                    attempt,
                    self.max_retries
                )

                if attempt == self.max_retries:
                    logger.error("Apollo connection failed after retries")
                    raise ApolloAPIError("Apollo connection failed")

                time.sleep(2 * attempt)

            except requests.exceptions.RequestException as e:

                logger.exception("Apollo request exception")

                raise ApolloAPIError(
                    f"Apollo request failed: {str(e)}"
                )

        logger.critical("Apollo API failed after max retries")

        raise ApolloAPIError(
            "Apollo API failed after max retries"
        )