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

    if not provider or not model or not api_key:
        raise ValueError(
            "Config must contain llm.provider, llm.model, and llm.api_key."
        )

    return LLMConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
    )
