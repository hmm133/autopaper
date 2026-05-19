from __future__ import annotations

import json
import urllib.request
import urllib.error
import time

from app.config import LLMConfig
from app.providers.base import LLMMessage, LLMProvider, extract_json_object


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        raw_base_url = (config.base_url or _default_base_url(config.provider)).rstrip("/")
        if _should_append_v1(raw_base_url, config.provider):
            raw_base_url = raw_base_url + "/v1"
        self.base_url = raw_base_url

    def create_json(self, messages: list[LLMMessage], schema: dict) -> dict:
        url = f"{self.base_url}/chat/completions"
        last_parse_error: Exception | None = None
        last_text_preview = ""
        last_http_error: RuntimeError | None = None
        for json_mode in _candidate_json_modes(self.config):
            for attempt in range(self.config.retries):
                payload = {
                    "model": self.config.model,
                    "messages": [
                        {"role": message.role, "content": message.content}
                        for message in messages
                    ],
                    "max_tokens": self.config.max_tokens,
                }
                if json_mode == "json_object":
                    payload["response_format"] = {
                        "type": "json_object",
                    }
                elif json_mode == "json_schema":
                    payload["response_format"] = {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "autopaper_output",
                            "schema": schema,
                        },
                    }
                request = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "Authorization": f"Bearer {self.config.api_key}",
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                        body = json.loads(response.read().decode("utf-8"))
                except urllib.error.HTTPError as exc:
                    error_body = exc.read().decode("utf-8", errors="ignore")
                    if _should_fallback_without_response_format(exc.code, error_body, json_mode, self.config):
                        last_http_error = RuntimeError(
                            f"LLM HTTP {exc.code} rejected response_format for provider={self.config.provider} model={self.config.model}; falling back to prompt_only."
                        )
                        break
                    raise RuntimeError(
                        f"LLM HTTP {exc.code} for provider={self.config.provider} model={self.config.model} url={url}: {error_body}"
                    ) from exc
                except urllib.error.URLError as exc:
                    raise RuntimeError(
                        f"LLM URL error for provider={self.config.provider} model={self.config.model} url={url}: {exc}"
                    ) from exc

                choices = body.get("choices", [])
                if not choices:
                    raise ValueError(f"Model returned no choices: {body}")
                content = choices[0].get("message", {}).get("content")
                if isinstance(content, list):
                    text = "".join(
                        part.get("text", "")
                        for part in content
                        if isinstance(part, dict)
                    )
                else:
                    text = content or ""

                if text.strip():
                    last_text_preview = text[:1200]
                    try:
                        return json.loads(extract_json_object(text))
                    except (json.JSONDecodeError, ValueError) as exc:
                        last_parse_error = exc
                        time.sleep(1 + attempt)
                        continue

                time.sleep(1 + attempt)

        if last_parse_error is not None:
            raise ValueError(
                f"Model returned non-parseable JSON after retries: {last_parse_error}. Preview: {last_text_preview}"
            ) from last_parse_error
        if last_http_error is not None:
            raise last_http_error
        raise ValueError("Model returned empty content after retries.")


def _default_base_url(provider: str) -> str:
    provider_name = provider.lower()
    if provider_name == "deepseek-compatible":
        return "https://api.deepseek.com/v1"
    if provider_name == "kimi-compatible":
        return "https://api.moonshot.ai/v1"
    if provider_name == "qwen-compatible":
        return "https://dashscope.aliyuncs.com/compatible-mode/v1"
    return "https://api.openai.com/v1"


def _should_append_v1(base_url: str, provider: str) -> bool:
    provider_name = provider.lower()
    if provider_name not in {
        "deepseek-compatible",
        "kimi-compatible",
        "qwen-compatible",
        "openai",
        "openai-compatible",
    }:
        return False
    return not base_url.endswith("/v1")


def _resolve_json_mode(config: LLMConfig) -> str:
    if config.json_mode != "auto":
        return config.json_mode

    provider_name = config.provider.lower()
    model_name = config.model.lower()

    if provider_name == "kimi-compatible" and "thinking" in model_name:
        return "prompt_only"

    if provider_name in {"deepseek-compatible", "kimi-compatible", "qwen-compatible"}:
        return "json_object"
    if "qwen" in model_name or "kimi" in model_name or "moonshot" in model_name or "deepseek" in model_name:
        return "json_object"
    return "json_schema"


def _candidate_json_modes(config: LLMConfig) -> list[str]:
    primary = _resolve_json_mode(config)
    if config.json_mode != "auto":
        return [primary]
    if primary == "prompt_only":
        return [primary]
    return [primary, "prompt_only"]


def _should_fallback_without_response_format(
    status_code: int,
    error_body: str,
    json_mode: str,
    config: LLMConfig,
) -> bool:
    if config.json_mode != "auto":
        return False
    if json_mode == "prompt_only":
        return False
    if status_code not in {400, 404, 422}:
        return False
    lowered = error_body.lower()
    return any(
        token in lowered
        for token in {
            "response_format",
            "json_schema",
            "json_object",
            "unsupported",
            "not support",
            "invalid parameter",
            "unknown parameter",
        }
    )

