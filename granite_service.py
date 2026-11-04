"""
granite_service.py — shared IBM watsonx.ai LLM client for Smart Study Generator Agent.

All five agents call get_granite_service() to obtain the singleton GraniteService
instance rather than creating their own ModelInference objects.

ROOT CAUSE NOTE
---------------
ibm/granite-4-h-small is a chat/instruct model.  Calling generate_text() on it
sends a raw completion prompt which the model treats as text to continue — it
echoes the JSON schema template rather than filling it in.  The correct API is
chat(), which accepts structured {"role": "system"/"user"} messages and returns
a proper assistant reply via response["choices"][0]["message"]["content"].

RATE LIMIT HANDLING
-------------------
IBM watsonx.ai free plans enforce a consumption limit.  When that limit is
reached the API returns HTTP 429 with error code "consumption_limit_reached".
GraniteService.generate() detects this, retries up to _MAX_RETRIES times with
exponential backoff (_RETRY_BASE_SECS * 2^attempt), and raises RateLimitError
if all retries are exhausted.  RateLimitError is a distinct exception type so
that callers (orchestrator, UI) can surface a user-friendly message rather than
a raw traceback.
"""

import json
import logging
import re
import time

import config

from ibm_watsonx_ai import Credentials
from ibm_watsonx_ai.foundation_models import ModelInference

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate-limit configuration
# ---------------------------------------------------------------------------

# Maximum number of retry attempts after a 429 response.
# Keeping this small (3) avoids hammering the quota further.
_MAX_RETRIES = 3

# Base wait time in seconds for the first retry.  Subsequent retries double
# this value: 5s → 10s → 20s.
_RETRY_BASE_SECS = 5


class RateLimitError(RuntimeError):
    """Raised when IBM watsonx.ai returns HTTP 429 / consumption_limit_reached
    and all retry attempts have been exhausted.

    The message is intentionally human-readable so it can be shown directly
    in the Streamlit UI without further formatting.
    """


def _is_rate_limit_error(exc: Exception) -> bool:
    """Return True when *exc* indicates an IBM 429 rate-limit response.

    Checks the string representation of the exception for the HTTP status
    code 429 or the error codes IBM uses for quota exhaustion.
    """
    text = str(exc).lower()
    return (
        "429" in text
        or "consumption_limit_reached" in text
        or "rate limit" in text
        or "too many requests" in text
        or "quota" in text
    )


class GraniteService:
    """Thin wrapper around ibm-watsonx-ai ModelInference using the chat API.

    The ModelInference client is created once in __init__ and reused across
    all generate() calls to avoid repeated credential instantiation overhead.
    """

    def __init__(self) -> None:
        credentials = Credentials(
            url=config.IBM_ENDPOINT_URL,
            api_key=config.IBM_API_KEY,
        )
        self._model = ModelInference(
            model_id=config.GRANITE_MODEL_ID,
            credentials=credentials,
            project_id=config.IBM_PROJECT_ID,
        )

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = None,
    ) -> str:
        """Call the Granite model via the chat API and return the reply as a string.

        Uses model.chat() with proper system/user message roles, which is the
        correct interface for ibm/granite-4-h-small (a chat/instruct model).

        Args:
            prompt: The user message content.
            system_prompt: Optional system instruction prepended as a system message.
            max_tokens: Maximum tokens to generate; defaults to config.MAX_TOKENS.

        Returns:
            The assistant's reply text, stripped of leading/trailing whitespace.

        Raises:
            RuntimeError: If the IBM watsonx.ai API call fails for any reason.
        """
        if max_tokens is None:
            max_tokens = config.MAX_TOKENS

        # Build the chat messages list
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        params = {
            "max_tokens": max_tokens,
            "temperature": config.TEMPERATURE,
        }

        # ── Retry loop with exponential backoff for 429 rate-limit errors ─────
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):  # attempt 0 is the first try
            if attempt > 0:
                wait_secs = _RETRY_BASE_SECS * (2 ** (attempt - 1))  # 5, 10, 20 …
                logger.warning(
                    "GraniteService: rate-limit hit, waiting %ds before retry %d/%d",
                    wait_secs, attempt, _MAX_RETRIES,
                )
                print(
                    f"[GraniteService] 429 rate-limit — waiting {wait_secs}s "
                    f"(retry {attempt}/{_MAX_RETRIES})"
                )
                time.sleep(wait_secs)

            try:
                response = self._model.chat(messages=messages, params=params)
            except Exception as exc:
                if _is_rate_limit_error(exc):
                    last_exc = exc
                    if attempt < _MAX_RETRIES:
                        continue  # go to the next retry
                    # All retries exhausted — raise the user-friendly error
                    raise RateLimitError(
                        "IBM watsonx.ai free usage limit reached. "
                        "Please wait a few minutes and try again."
                    ) from exc
                # Any other error — raise immediately, no retry
                raise RuntimeError(
                    f"IBM watsonx.ai chat() failed for model "
                    f"'{config.GRANITE_MODEL_ID}': {exc}"
                ) from exc

            # Successful response — break out of the retry loop
            break
        else:
            # Should never reach here, but guard just in case
            raise RateLimitError(
                "IBM watsonx.ai free usage limit reached. "
                "Please wait a few minutes and try again."
            )

        # ── Extract content from the standard OpenAI-compatible response ──────
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            safe_repr = str(response)[:500] if response else "<empty response>"
            print(f"[GraniteService] Unexpected chat() response structure: {safe_repr}")
            raise RuntimeError(
                f"IBM watsonx.ai chat() returned an unexpected response structure "
                f"for model '{config.GRANITE_MODEL_ID}'. "
                f"Response keys: {list(response.keys()) if isinstance(response, dict) else type(response)}"
            ) from exc

        text = content.strip() if isinstance(content, str) else str(content).strip()
        print(
            f"[GraniteService] chat() reply: {len(text)} chars, "
            f"max_tokens={max_tokens}, finish_reason="
            f"{response.get('choices', [{}])[0].get('finish_reason', '?')}"
        )
        return text

    def generate_json(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = None,
    ) -> dict:
        """Call generate() via chat() and parse the result as JSON.

        Extraction strategy (applied in order until one succeeds):
        1. Strip markdown code fences anywhere in the response, then json.loads().
        2. Brace-depth scan to find the first complete {...} block in the raw text.
        3. Same scan on the fence-stripped text.
        4. Raise ValueError with the full raw response printed for diagnosis.

        Returns:
            Parsed JSON as a dict.

        Raises:
            RuntimeError: Propagated from generate() on API failure.
            ValueError: If no valid JSON object can be extracted.
        """
        raw_response = self.generate(
            prompt=prompt, system_prompt=system_prompt, max_tokens=max_tokens
        )

        # Always print the raw response for debugging in the terminal
        print(f"[GraniteService] Raw response (first 1000 chars):\n{raw_response[:1000]}")
        logger.debug("Granite raw response:\n%s", raw_response)

        # ── Attempt 1: strip ALL code fences, then parse ───────────────────────
        fence_stripped = re.sub(
            r"```(?:json)?\s*", "", raw_response, flags=re.IGNORECASE
        ).strip()
        fence_stripped = re.sub(r"```\s*$", "", fence_stripped).strip()

        try:
            return json.loads(fence_stripped)
        except json.JSONDecodeError:
            pass

        # ── Attempt 2: extract first {...} block from raw response ─────────────
        json_obj = _extract_json_object(raw_response)
        if json_obj is not None:
            return json_obj

        # ── Attempt 3: extract first {...} block from fence-stripped text ───────
        json_obj = _extract_json_object(fence_stripped)
        if json_obj is not None:
            return json_obj

        # Nothing worked — raise with the full raw response
        raise ValueError(
            f"Granite returned invalid JSON.\n"
            f"Raw response (full):\n{raw_response}\n"
            f"---\nThis is Granite's actual output — not a code error. "
            f"The model did not return a JSON object."
        )


# ── JSON extraction helper ────────────────────────────────────────────────────

def _extract_json_object(text: str) -> dict | None:
    """Scan *text* for the first top-level ``{...}`` block and parse it.

    Returns the parsed dict on success, or None if no valid JSON object is found.
    Handles cases where Granite prefixes its answer with explanatory prose.
    """
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape_next = False

    for i in range(start, len(text)):
        ch = text[i]

        if escape_next:
            escape_next = False
            continue

        if ch == "\\" and in_string:
            escape_next = True
            continue

        if ch == '"' and not escape_next:
            in_string = not in_string
            continue

        if in_string:
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start : i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    next_start = text.find("{", i + 1)
                    if next_start == -1:
                        return None
                    start = next_start
                    depth = 0
                    in_string = False

    return None


# ── IBM Embedding Function (ChromaDB-compatible) ─────────────────────────────

from chromadb import Documents, EmbeddingFunction, Embeddings as ChromaEmbeddings


class IBMEmbeddingFunction(EmbeddingFunction[Documents]):
    """ChromaDB-compatible embedding function backed by IBM watsonx.ai.

    Replaces the default sentence-transformers model so no local model is
    downloaded or run on CPU.  Uses the same IBM credentials already
    configured for the Granite chat model.

    Subclasses chromadb.EmbeddingFunction so ChromaDB 1.5+ accepts it
    without errors about missing ``name``, ``get_config``, or
    ``build_from_config``.
    """

    def __init__(self) -> None:
        from ibm_watsonx_ai import Credentials
        from ibm_watsonx_ai.foundation_models import Embeddings

        credentials = Credentials(
            url=config.IBM_ENDPOINT_URL,
            api_key=config.IBM_API_KEY,
        )
        self._ibm_embeddings = Embeddings(
            model_id=config.EMBEDDING_MODEL_ID,
            credentials=credentials,
            project_id=config.IBM_PROJECT_ID,
        )

    def __call__(self, input: Documents) -> ChromaEmbeddings:  # noqa: A002
        """Embed *input* texts and return a list of float vectors."""
        return self._ibm_embeddings.embed_documents(texts=list(input))

    @staticmethod
    def name() -> str:
        return "IBMEmbeddingFunction"

    def get_config(self) -> dict:
        return {
            "model_id": config.EMBEDDING_MODEL_ID,
            "endpoint_url": config.IBM_ENDPOINT_URL,
            "project_id": config.IBM_PROJECT_ID,
        }

    @staticmethod
    def build_from_config(cfg: dict) -> "IBMEmbeddingFunction":
        return IBMEmbeddingFunction()


# ── Module-level singletons ───────────────────────────────────────────────────

_granite_service_instance: "GraniteService | None" = None
_ibm_embedding_fn_instance: "IBMEmbeddingFunction | None" = None


def get_granite_service() -> GraniteService:
    """Return the shared GraniteService singleton, creating it on first call."""
    global _granite_service_instance
    if _granite_service_instance is None:
        _granite_service_instance = GraniteService()
    return _granite_service_instance


def get_ibm_embedding_function() -> IBMEmbeddingFunction:
    """Return the shared IBMEmbeddingFunction singleton, creating it on first call."""
    global _ibm_embedding_fn_instance
    if _ibm_embedding_fn_instance is None:
        _ibm_embedding_fn_instance = IBMEmbeddingFunction()
    return _ibm_embedding_fn_instance
