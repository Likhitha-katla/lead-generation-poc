# Gemini API client with retry logic and rate limiting
# gemini_client.py
import re
import time
import asyncio
import logging
import threading
import os
import random
import json
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv()

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


def _get_gemini_model_fallbacks() -> list[str]:
    raw = _get_env("GEMINI_MODEL_FALLBACKS", "gemini-2.0-flash,gemini-2.5-flash-lite").strip()
    fallbacks = [model.strip() for model in raw.split(",") if model.strip()]
    # Keep the primary model first, then any configured fallbacks.
    primary = _get_gemini_model()
    models = [primary]
    for model in fallbacks:
        if model not in models:
            models.append(model)
    return models


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

    # Some Gemini tool combinations (e.g., using `tools`) do not support
    # forcing a response MIME type like `application/json`. If both are
    # present, prefer the tools and drop the MIME type to avoid INVALID_ARGUMENT.
    if config is not None and hasattr(config, 'tools') and getattr(config, 'tools') and getattr(config, 'response_mime_type', None):
        logger.warning(
            "Dropping response_mime_type because tools are enabled (unsupported combination)",
            extra={"response_mime_type": getattr(config, 'response_mime_type'), "tools": True},
        )
        try:
            # Rebuild config without response_mime_type
            cfg_dict = {k: v for k, v in config_kwargs.items() if k != 'response_mime_type'}
            config = types.GenerateContentConfig(**cfg_dict) if cfg_dict else None
        except Exception:
            # If rebuilding fails, fall back to original config (let server return the error)
            pass

    max_retries = _get_max_retries()
    timeout = _get_timeout()
    retry_delay = _get_retry_delay()
    model_candidates = _get_gemini_model_fallbacks()
    last_error = None

    for model_index, model in enumerate(model_candidates):
        logger.info("Using Gemini model", extra={"model": model, "model_index": model_index})

        for attempt in range(max_retries):
            try:
                await rate_limiter.wait()

                logger.debug(
                    "Gemini API call",
                    extra={
                        "attempt": attempt + 1,
                        "max_retries": max_retries,
                        "model": model,
                        "expect_json": expect_json,
                        "use_google_search": use_google_search,
                    },
                )

                response_text = await asyncio.wait_for(
                    asyncio.to_thread(
                        _sync_generate,
                        client,
                        model,
                        prompt,
                        config,
                    ),
                    timeout=timeout,
                )

                logger.debug("Gemini API call successful", extra={"model": model})

                # If caller requested JSON and we didn't disable MIME type via tools,
                # attempt to parse and return a Python object (dict/list).
                if expect_json:
                    try:
                        parsed = json.loads(response_text) if isinstance(response_text, str) else response_text
                        return parsed
                    except Exception:
                        # Fall through to return raw text so callers can attempt extraction
                        logger.debug("Failed to parse response as JSON; returning raw text", extra={"model": model})

                return response_text

            except asyncio.TimeoutError:
                last_error = f"Gemini API timeout after {timeout}s"
                logger.warning("Gemini timeout", extra={"attempt": attempt + 1, "timeout": timeout, "model": model})

            except Exception as e:
                error_str = str(e)
                last_error = error_str

                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    if "daily" in error_str.lower() or "quota" in error_str.lower():
                        logger.warning(
                            "Gemini quota warning (retrying)",
                            extra={"attempt": attempt + 1, "model": model, "error": error_str},
                        )

                    retry_match = re.search(r"retry in (\d+(\.\d+)?)s", error_str)
                    if not retry_match:
                        retry_match = re.search(r"retryDelay': '(\d+(\.\d+)?)s'", error_str)

                    if retry_match:
                        wait_time = float(retry_match.group(1)) + 1.0
                        logger.warning(
                            "Rate limit hit, waiting %ss before retry",
                            wait_time,
                            extra={"attempt": attempt + 1, "model": model},
                        )
                        await asyncio.sleep(wait_time)
                        continue

                # Look for common Retry-After patterns (seconds)
                retry_after_match = re.search(r"Retry-After[:=]\s*(\d+)", error_str, re.IGNORECASE)
                if retry_after_match:
                    wait_time = float(retry_after_match.group(1))
                    logger.warning(
                        "Retry-After header present, waiting %ss before retry",
                        wait_time,
                        extra={"attempt": attempt + 1, "model": model},
                    )
                    await asyncio.sleep(wait_time)
                    continue

                logger.warning(
                    "Gemini API failed",
                    extra={"attempt": attempt + 1, "model": model, "error": error_str},
                )

                # If the model is unavailable (high demand / 503), move to next fallback model immediately.
                if "503" in error_str or "UNAVAILABLE" in error_str:
                    logger.warning(
                        "Gemini model unavailable, switching to next fallback",
                        extra={"model": model, "attempt": attempt + 1, "error": error_str},
                    )
                    break

            if attempt < max_retries - 1:
                # Exponential backoff with small random jitter
                base_delay = retry_delay * (2 ** attempt)
                jitter = random.uniform(0, min(1.0, retry_delay))
                delay = base_delay + jitter
                logger.info("Retrying Gemini", extra={"delay_seconds": round(delay, 2), "model": model})
                await asyncio.sleep(delay)

        # Try next fallback model if available.
        if model_index < len(model_candidates) - 1:
            next_model = model_candidates[model_index + 1]
            logger.warning("Switching Gemini model fallback", extra={"from_model": model, "to_model": next_model})
            continue

        break

    error_msg = f"Gemini API failed after {max_retries} attempts on all models: {last_error}"
    logger.error(error_msg)
    raise ExternalServiceError("Gemini", error_msg)
