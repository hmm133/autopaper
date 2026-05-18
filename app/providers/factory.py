from __future__ import annotations

from app.config import LLMConfig
from app.providers.base import LLMProvider
from app.providers.openai_compatible import OpenAICompatibleProvider


def build_provider(config: LLMConfig) -> LLMProvider:
    provider = config.provider.lower()
    if provider in {"openai", "openai-compatible", "deepseek-compatible"}:
        return OpenAICompatibleProvider(config)
    raise ValueError(f"Unsupported provider: {config.provider}")
