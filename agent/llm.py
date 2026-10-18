"""Shared LLM helpers with a provider switch (PROVIDER in .env).

  PROVIDER=gemini  (default) native Gemini client. The native client is needed because
                   Gemini 3 requires 'thought signatures' to be sent back after tool
                   calls, which the OpenAI-compat layer drops (400 INVALID_ARGUMENT).
  PROVIDER=ollama  local model through Ollama: no quota, no cost, runs on your GPU.
"""
import os

from dotenv import load_dotenv

load_dotenv()

PROVIDER = os.getenv("PROVIDER", "gemini").strip().lower()

_DEFAULTS = {
    "gemini": ("gemini-3.8-flash", "gemini-3.6-flash"),
    "ollama": ("granite4.1:8b", "granite4.1:8b"),
}
if PROVIDER not in _DEFAULTS:
    raise SystemExit(f"PROVIDER must be 'gemini' or 'ollama', got {PROVIDER!r}")

AGENT_MODEL = os.getenv("AGENT_MODEL", _DEFAULTS[PROVIDER][0])
JUDGE_MODEL = os.getenv("JUDGE_MODEL", _DEFAULTS[PROVIDER][1])

_LIMITER = None
if PROVIDER == "gemini":
    from langchain_core.rate_limiters import InMemoryRateLimiter

    # The free tier has low per-minute limits. One limiter is shared by the agent and
    # the judge so total request rate stays under it (0.1 = 6 requests/minute).
    _LIMITER = InMemoryRateLimiter(
        requests_per_second=float(os.getenv("LLM_RPS", "0.1")),
        check_every_n_seconds=0.2,
        max_bucket_size=1,
    )


def _gemini_key() -> str:
    # OPENAI_API_KEY is accepted as a fallback so an old .env keeps working
    return (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            or os.getenv("OPENAI_API_KEY") or "")


def make_llm(model: str, json_mode: bool = False):
    """Chat model for the configured provider. json_mode forces JSON output (judge)."""
    if PROVIDER == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=model,
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            temperature=0,  # reproducible runs for evals
            # A small context window keeps VRAM use (and heat) down. Our prompts are short.
            num_ctx=int(os.getenv("OLLAMA_NUM_CTX", "4096")),
            keep_alive=os.getenv("OLLAMA_KEEP_ALIVE", "2m"),  # unload from VRAM when idle
            # Hard cap on generated tokens. At temperature 0 a small model can fall into a
            # repetition loop (seen on Georgian) and generate until the context is full.
            num_predict=int(os.getenv("OLLAMA_NUM_PREDICT", "300" if json_mode else "512")),
            format="json" if json_mode else None,
        )

    from langchain_google_genai import ChatGoogleGenerativeAI

    extra = {"response_mime_type": "application/json"} if json_mode else {}
    # No temperature=0: Google advises leaving it at the default for Gemini 3.
    return ChatGoogleGenerativeAI(
        model=model, google_api_key=_gemini_key(), max_retries=2, timeout=90,
        rate_limiter=_LIMITER, **extra
    )


def as_text(content) -> str:
    """Flatten message content (str or list of blocks) to plain text."""
    if isinstance(content, list):
        return "".join(
            b.get("text", "") if isinstance(b, dict) else str(b) for b in content
        )
    return str(content)
