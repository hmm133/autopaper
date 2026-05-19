from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


CONFIG_ENV_PATH = "AUTOPAPER_CONFIG"
DEFAULT_CONFIG_PATH = Path("config/autopaper_config.json")


@dataclass
class LLMConfig:
    provider: str
    model: str
    api_key: str
    base_url: str | None = None
    json_mode: str = "auto"
    max_tokens: int = 4000
    timeout_seconds: int = 180
    retries: int = 3


def load_llm_config(config_path: Path | None = None) -> LLMConfig:
    path = config_path or Path(os.environ.get(CONFIG_ENV_PATH, DEFAULT_CONFIG_PATH))
    if not path.exists():
        raise FileNotFoundError(
            f"LLM config file not found: {path}. Create it before running extraction."
        )

    payload = json.loads(path.read_text(encoding="utf-8"))
    llm = payload.get("llm", {})
    provider = llm.get("provider")
    model = llm.get("model")
    api_key = llm.get("api_key")
    base_url = llm.get("base_url")
    json_mode = llm.get("json_mode", "auto")
    max_tokens = int(llm.get("max_tokens", 4000))
    timeout_seconds = int(llm.get("timeout_seconds", 180))
    retries = int(llm.get("retries", 3))

    if not provider or not model or not api_key:
        raise ValueError(
            "Config must contain llm.provider, llm.model, and llm.api_key."
        )
    if json_mode not in {"auto", "json_schema", "json_object", "prompt_only"}:
        raise ValueError(
            "llm.json_mode must be one of: auto, json_schema, json_object, prompt_only."
        )
    if max_tokens <= 0 or timeout_seconds <= 0 or retries <= 0:
        raise ValueError("llm.max_tokens, llm.timeout_seconds, and llm.retries must be positive integers.")

    return LLMConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
        json_mode=json_mode,
        max_tokens=max_tokens,
        timeout_seconds=timeout_seconds,
        retries=retries,
    )
