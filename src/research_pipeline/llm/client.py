"""LLM configuration: the one place that decides which provider and model are used.

Switching provider is a .env change, not a code change:
    LLM_MODEL=google:gemini-3.8-flash        (needs GOOGLE_API_KEY)
    LLM_MODEL=anthropic:claude-haiku-4-5     (needs ANTHROPIC_API_KEY + pydantic-ai-slim[anthropic])

This module deliberately does not import pydantic_ai; only agents/ does.
"""

import os

from dotenv import load_dotenv

DEFAULT_MODEL = "google:gemini-3.8-flash"
TEMPERATURE = 0.0  # reduce run-to-run variation; wording can still vary between runs
OUTPUT_RETRIES = 1  # invalid structured output: send the validation error back once, then fail the step

_KEY_FOR_PROVIDER = {
    "google": ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
}


class LLMConfigError(RuntimeError):
    """Raised at start-up when the LLM cannot be configured (fail fast, before any work)."""


def _check_key(model: str) -> str:
    provider = model.split(":", 1)[0]
    keys = _KEY_FOR_PROVIDER.get(provider, ())
    if keys and not any(os.getenv(k) for k in keys):
        raise LLMConfigError(f"Model '{model}' needs {' or '.join(keys)} in .env")
    return model


def model_name() -> str:
    """Return the configured model string, e.g. 'google:gemini-3.8-flash'.

    Checks the API key is present so a missing key fails at start-up with a clear
    message instead of halfway through a run.
    """
    load_dotenv()
    return _check_key(os.getenv("LLM_MODEL", DEFAULT_MODEL))


def fallback_model_names() -> list[str]:
    """Optional fallback chain, tried in order only when the previous model fails with a
    provider error (overloaded, rate-limited, down). Comma-separated in .env:
        LLM_FALLBACK_MODEL=google:gemini-3.5-flash,google:gemini-3.1-flash-lite
    Empty or unset disables fallback."""
    load_dotenv()
    raw = os.getenv("LLM_FALLBACK_MODEL", "")
    return [_check_key(m.strip()) for m in raw.split(",") if m.strip()]
