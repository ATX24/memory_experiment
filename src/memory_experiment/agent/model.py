"""Model factory: chat model served through the Vercel AI Gateway
(OpenAI-compatible endpoint) or any OpenAI-compatible server named by
AI_GATEWAY_BASE_URL, e.g. the local Claude Code gateway in gateway/.
Set AI_GATEWAY_API_KEY (or VERCEL_OIDC_TOKEN) in the environment or .env."""
from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

DEFAULT_GATEWAY = "https://ai-gateway.vercel.sh/v1"


def make_model(model: str, temperature: float = 0.0, timeout: float = 120.0) -> ChatOpenAI:
    load_dotenv()
    base_url = os.environ.get("AI_GATEWAY_BASE_URL", DEFAULT_GATEWAY)
    key = os.environ.get("AI_GATEWAY_API_KEY") or os.environ.get("VERCEL_OIDC_TOKEN")
    if not key:
        raise RuntimeError("AI_GATEWAY_API_KEY (or VERCEL_OIDC_TOKEN) is not set; put it in .env")
    return ChatOpenAI(model=model, api_key=key, base_url=base_url, temperature=temperature, timeout=timeout, max_retries=3)
