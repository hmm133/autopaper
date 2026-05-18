from __future__ import annotations

import json
import urllib.request
import urllib.error
import time

from app.config import LLMConfig
from app.providers.base import LLMMessage, LLMProvider


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        raw_base_url = (config.base_url or "https://api.openai.com/v1").rstrip("/")
        if config.provider.lower() == "deepseek-compatible" and not raw_base_url.endswith("/v1"):
            raw_base_url = raw_base_url + "/v1"
        self.base_url = raw_base_url

    def create_json(self, messages: list[LLMMessage], schema: dict) -> dict:
        url = f"{self.base_url}/chat/completions"
        provider_name = self.config.provider.lower()
        last_parse_error: Exception | None = None
        last_text_preview = ""
        for attempt in range(3):
            payload = {
                "model": self.config.model,
                "messages": [
                    {"role": message.role, "content": message.content}
                    for message in messages
                ],
                "max_tokens": 4000,
            }
            if provider_name == "deepseek-compatible":
                payload["response_format"] = {
                    "type": "json_object",
                }
            else:
                payload["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "paper_units",
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
                with urllib.request.urlopen(request, timeout=180) as response:
                    body = json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                error_body = exc.read().decode("utf-8", errors="ignore")
                raise RuntimeError(
                    f"LLM HTTP {exc.code} for provider={self.config.provider} model={self.config.model} url={url}: {error_body}"
                ) from exc
            except urllib.error.URLError as exc:
                raise RuntimeError(
                    f"LLM URL error for provider={self.config.provider} model={self.config.model} url={url}: {exc}"
                ) from exc

            content = body["choices"][0]["message"]["content"]
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
                    return json.loads(_extract_json_object(text))
                except (json.JSONDecodeError, ValueError) as exc:
                    last_parse_error = exc
                    time.sleep(1 + attempt)
                    continue

            time.sleep(1 + attempt)

        if last_parse_error is not None:
            raise ValueError(
                f"Model returned non-parseable JSON after retries: {last_parse_error}. Preview: {last_text_preview}"
            ) from last_parse_error
        raise ValueError("Model returned empty content after retries.")


def _extract_json_object(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1:
        raise ValueError(f"Model did not return JSON content: {text[:400]}")
    if end == -1 or end <= start:
        raise ValueError(f"Model returned truncated JSON content: {text[:1200]}")
    return stripped[start : end + 1]
