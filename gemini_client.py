# Gemini API client with retry logic and rate limiting
import re
import time
import asyncio
import logging
import threading
import os
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv()

# Optional Google GenAI SDK. We guard import so the project can still
# run in degraded mode (generate_with_retry will raise a clear error
# if the SDK isn't available or not configured).
try:
    from google import genai  # type: ignore
    from google.genai import types  # type: ignore
    HAS_GOOGLE = True
except Exception:
    genai = None
    types = None
    HAS_GOOGLE = False


def _get_env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def _get_gemini_api_key() -> str:
    return _get_env("GEMINI_API_KEY", "").strip()


def _get_gemini_model() -> str:
    return _get_env("GEMINI_MODEL", "gemini-2.5-flash-lite").strip() or "gemini-2.5-flash"


def _get_max_retries() -> int:
    return int(_get_env("GEMINI_MAX_RETRIES", "3"))


def _get_retry_delay() -> float:
    return float(_get_env("GEMINI_RETRY_DELAY", "1.0"))


def _get_requests_per_minute() -> int:
    return int(_get_env("GEMINI_REQUESTS_PER_MINUTE", "60"))


def _get_timeout() -> int:
    return int(_get_env("GEMINI_TIMEOUT", "30"))


# Lightweight exceptions to avoid depending on a core package
class ConfigurationError(Exception):
    pass


class ExternalServiceError(Exception):
    def __init__(self, service_name: str, message: str):
        super().__init__(f"{service_name}: {message}")


class RateLimiter:
    """Fixed-interval rate limiter for API calls"""
    
    def __init__(self, requests_per_minute: int):
        self.interval = 60.0 / requests_per_minute
        self.last_request = 0
        self._lock = asyncio.Lock()
    
    async def wait(self):
        async with self._lock:
            now = time.time()
            elapsed = now - self.last_request
            if elapsed < self.interval:
                wait_time = self.interval - elapsed
                logger.debug("Rate limiting", extra={"wait_seconds": round(wait_time, 2)})
                await asyncio.sleep(wait_time)
            self.last_request = time.time()


rate_limiter = RateLimiter(_get_requests_per_minute())


# Thread-safe singleton client
_gemini_client = None
_client_lock = threading.Lock()


def get_gemini_client(api_key: Optional[str] = None):
    """Get or create the Gemini client instance"""
    global _gemini_client

    resolved_api_key = (api_key or _get_gemini_api_key()).strip()

    if _gemini_client is not None and api_key is None:
        return _gemini_client

    with _client_lock:
        # Double-check after acquiring lock
        if _gemini_client is None or api_key is not None:
            if not HAS_GOOGLE:
                raise ConfigurationError(
                    "google.genai SDK is not installed. Add google-genai to requirements and install dependencies."
                )
            if not resolved_api_key:
                raise ConfigurationError("GEMINI_API_KEY is not configured")
            client = genai.Client(api_key=resolved_api_key)
            if api_key is None:
                _gemini_client = client
            logger.info("Gemini client initialized")

            return client

    return _gemini_client


def _sync_generate(client, model: str, prompt: str, config) -> str:
    """Run synchronous Gemini generation call."""
    # Ensure contents is a list (SDKs often accept a sequence of content parts)
    contents_arg = prompt if isinstance(prompt, (list, tuple)) else [prompt]

    response = client.models.generate_content(
        model=model,
        contents=contents_arg,
        config=config
    )

    # Try several ways to extract text from the SDK response
    text = None

    # Common simple attribute
    if hasattr(response, 'text'):
        try:
            text_val = response.text
            if isinstance(text_val, str) and text_val.strip():
                text = text_val
        except Exception:
            pass

    # Older/newer SDKs may expose candidates with nested parts
    if not text and hasattr(response, 'candidates') and response.candidates:
        try:
            candidate = response.candidates[0]
            if hasattr(candidate, 'content') and candidate.content:
                parts = getattr(candidate.content, 'parts', None)
                if parts:
                    text = "".join(getattr(part, 'text', '') for part in parts)
                else:
                    # Fallback to candidate.content as string
                    text = str(candidate.content)
        except Exception:
            pass

    # Some SDK shapes include 'output' or 'result' fields
    if not text:
        for attr in ('output', 'result', 'response', 'content'):
            if hasattr(response, attr):
                try:
                    val = getattr(response, attr)
                    if isinstance(val, str) and val.strip():
                        text = val
                        break
                    # If it's an object, try common nested locations
                    if hasattr(val, 'text') and isinstance(val.text, str) and val.text.strip():
                        text = val.text
                        break
                except Exception:
                    continue

    # As a last resort, try to stringify representative fields for debugging
    if not text:
        try:
            # Build a concise debug summary (avoid huge dumps)
            rep = []
            for name in ('text', 'candidates', 'output', 'result'):
                if hasattr(response, name):
                    try:
                        val = getattr(response, name)
                        rep.append(f"{name}={repr(val)[:100]}")
                    except Exception:
                        rep.append(f"{name}=<error>")
            logger.debug("Gemini raw response summary: %s", "; ".join(rep))
        except Exception:
            logger.debug("Gemini raw response repr: %s", repr(response))

    if not text:
        raise ValueError(f"Gemini returned empty response (summary: {rep if 'rep' in locals() else repr(response)})")

    return text

async def generate_with_retry(
    prompt: str,
    expect_json: bool = False,
    use_google_search: bool = False,
    system_instruction: Optional[str] = None,
    api_key: Optional[str] = None,
) -> str:

    client = get_gemini_client(api_key=api_key)
    
    config_kwargs = {}
    
    if system_instruction:
        config_kwargs["system_instruction"] = system_instruction
    
    if expect_json:
        config_kwargs["response_mime_type"] = "application/json"
    
    if use_google_search:
        config_kwargs["tools"] = [types.Tool(google_search=types.GoogleSearch())]
    
    config = types.GenerateContentConfig(**config_kwargs) if config_kwargs else None
    
    last_error = None
    
    max_retries = _get_max_retries()
    timeout = _get_timeout()
    retry_delay = _get_retry_delay()
    model = _get_gemini_model()

    for attempt in range(max_retries):
        try:
            await rate_limiter.wait()
            
            logger.debug("Gemini API call", extra={
                "attempt": attempt + 1,
                "max_retries": max_retries,
                "expect_json": expect_json,
                "use_google_search": use_google_search
            })
            
            response_text = await asyncio.wait_for(
                asyncio.to_thread(
                    _sync_generate,
                    client,
                    model,
                    prompt,
                    config
                ),
                timeout=timeout
            )
            
            logger.debug("Gemini API call successful")
            return response_text
            
        except asyncio.TimeoutError:
            last_error = f"Gemini API timeout after {timeout}s"
            logger.warning("Gemini timeout", extra={"attempt": attempt + 1, "timeout": timeout})
            
        except Exception as e:
            error_str = str(e)
            last_error = error_str

            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                # Log quota/daily limit warnings but do NOT hard-stop; just retry
                if "daily" in error_str.lower() or "quota" in error_str.lower():
                    logger.warning("Gemini quota warning (retrying)", extra={"attempt": attempt + 1, "error": error_str})
                
                retry_match = re.search(r"retry in (\d+(\.\d+)?)s", error_str)
                if not retry_match:
                    retry_match = re.search(r"retryDelay': '(\d+(\.\d+)?)s'", error_str)
                
                if retry_match:
                    wait_time = float(retry_match.group(1)) + 1.0
                    logger.warning(
                        "Rate limit hit, waiting %ss before retry",
                        wait_time,
                        extra={"attempt": attempt + 1}
                    )
                    await asyncio.sleep(wait_time)
                    continue
            
            logger.warning("Gemini API failed", extra={"attempt": attempt + 1, "error": error_str})
        
        if attempt < max_retries - 1:
            delay = retry_delay * (2 ** attempt)
            logger.info("Retrying Gemini", extra={"delay_seconds": delay})
            await asyncio.sleep(delay)
    
    error_msg = f"Gemini API failed after {max_retries} attempts: {last_error}"
    logger.error(error_msg)
    raise ExternalServiceError("Gemini", f"Failed after {max_retries} attempts: {last_error}")
