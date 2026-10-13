"""Shared LLM helpers. Uses the native Gemini client because Gemini 3 requires
'thought signatures' to be sent back after tool calls, which the OpenAI-compat
layer drops (400 INVALID_ARGUMENT)."""
import os

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()


def _key() -> str:
    # OPENAI_API_KEY is accepted as a fallback so an existing .env keeps working
    return (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            or os.getenv("OPENAI_API_KEY") or "")


def make_llm(model: str, **kwargs) -> ChatGoogleGenerativeAI:
    # No temperature=0: Google advises leaving it at the default for Gemini 3.
    return ChatGoogleGenerativeAI(
        model=model, google_api_key=_key(), max_retries=6, timeout=90, **kwargs
    )


def as_text(content) -> str:
    """Gemini 3 may return content as a list of blocks; flatten to plain text."""
    if isinstance(content, list):
        return "".join(
            b.get("text", "") if isinstance(b, dict) else str(b) for b in content
        )
    return str(content)
