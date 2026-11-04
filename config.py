"""
config.py — centralised configuration for Smart Study Generator Agent.

Loads environment variables from a .env file (if present) and exposes them as
typed module-level constants.  Required variables raise a ValueError on import
if they are missing or empty; optional variables fall back to sensible defaults.
"""

import os
from dotenv import load_dotenv

# Load .env file into the environment (no-op if .env does not exist)
load_dotenv()


def _require(name: str) -> str:
    """Return the value of *name* from the environment, or raise ValueError."""
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(
            f"Required environment variable '{name}' is missing or empty. "
            "Copy .env.example to .env and fill in all required values."
        )
    return value


def _optional_int(name: str, default: int) -> int:
    """Return *name* as an int, falling back to *default* if absent or invalid."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _optional_float(name: str, default: float) -> float:
    """Return *name* as a float, falling back to *default* if absent or invalid."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


# ── Required ─────────────────────────────────────────────────────────────────
_missing: list[str] = []
_required_names = [
    "IBM_API_KEY",
    "IBM_ENDPOINT_URL",
    "IBM_PROJECT_ID",
    "GRANITE_MODEL_ID",
    "CHROMA_DB_PATH",
    "JSON_DATA_PATH",
]
for _name in _required_names:
    if not os.getenv(_name, "").strip():
        _missing.append(_name)

if _missing:
    raise ValueError(
        "The following required environment variables are missing or empty: "
        + ", ".join(_missing)
        + ". Copy .env.example to .env and fill in all required values."
    )

IBM_API_KEY: str = os.getenv("IBM_API_KEY", "").strip()
IBM_ENDPOINT_URL: str = os.getenv("IBM_ENDPOINT_URL", "").strip()
IBM_PROJECT_ID: str = os.getenv("IBM_PROJECT_ID", "").strip()
GRANITE_MODEL_ID: str = os.getenv("GRANITE_MODEL_ID", "").strip()
# Optional — defaults to IBM's standard retrieval embedding model.
# Add EMBEDDING_MODEL_ID=ibm/slate-125m-english-rtrvr-v2 to .env to override.
EMBEDDING_MODEL_ID: str = (
    os.getenv("EMBEDDING_MODEL_ID", "").strip()
    or "ibm/slate-125m-english-rtrvr-v2"
)
CHROMA_DB_PATH: str = os.getenv("CHROMA_DB_PATH", "").strip()
JSON_DATA_PATH: str = os.getenv("JSON_DATA_PATH", "").strip()

# ── Optional (with defaults) ─────────────────────────────────────────────────
# MAX_TOKENS: minimum recommended is 2048.  Values below 1500 will likely cause
# truncated JSON responses.  The default is 2048; override in .env if needed.
_raw_max_tokens = _optional_int("MAX_TOKENS", 2048)
if _raw_max_tokens < 1500:
    import warnings as _warnings
    _warnings.warn(
        f"MAX_TOKENS={_raw_max_tokens} in your .env is too low and will cause truncated "
        "JSON responses. Set MAX_TOKENS=2048 (or higher) in your .env file.",
        stacklevel=2,
    )
    _raw_max_tokens = 2048  # enforce minimum
MAX_TOKENS: int = _raw_max_tokens
TEMPERATURE: float = _optional_float("TEMPERATURE", 0.3)
CHUNK_SIZE: int = _optional_int("CHUNK_SIZE", 500)
CHUNK_OVERLAP: int = _optional_int("CHUNK_OVERLAP", 50)


if __name__ == "__main__":
    print("Configuration loaded successfully:")
    print(f"  IBM_ENDPOINT_URL  : {IBM_ENDPOINT_URL}")
    print(f"  IBM_PROJECT_ID    : {IBM_PROJECT_ID}")
    print(f"  GRANITE_MODEL_ID  : {GRANITE_MODEL_ID}")
    print(f"  EMBEDDING_MODEL_ID: {EMBEDDING_MODEL_ID}")
    print(f"  CHROMA_DB_PATH    : {CHROMA_DB_PATH}")
    print(f"  JSON_DATA_PATH   : {JSON_DATA_PATH}")
    print(f"  MAX_TOKENS       : {MAX_TOKENS}")
    print(f"  TEMPERATURE      : {TEMPERATURE}")
    print(f"  CHUNK_SIZE       : {CHUNK_SIZE}")
    print(f"  CHUNK_OVERLAP    : {CHUNK_OVERLAP}")
    print("  IBM_API_KEY      : [set]")
