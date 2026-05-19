from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from app.config import LLMConfig
from app.providers.base import LLMMessage, LLMProvider, extract_json_object


class AnthropicNativeProvider(LLMProvider):
    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self.base_url = (config.base_url or "https://api.anthropic.com").rstrip("/")

    def create_json(self, messages: list[LLMMessage], schema: dict) -> dict:
        url = f"{self.base_url}/v1/messages"
        last_parse_error: Exception | None = None
        last_text_preview = ""

        system_text = "\n\n".join(
            message.content
            for message in messages
            if message.role == "system" and message.content.strip()
        )
        anthropic_messages = [
            {
                "role": "user",
                "content": message.content,
            }
            for message in messages
            if message.role != "system" and message.content.strip()
        ]

        if not anthropic_messages:
            raise ValueError("Anthropic provider requires at least one non-system message.")

        for attempt in range(self.config.retries):
            payload = {
                "model": self.config.model,
                "max_tokens": self.config.max_tokens,
                "messages": anthropic_messages,
            }
            if system_text:
                payload["system"] = system_text

            request = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "x-api-key": self.config.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                    body = json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                error_body = exc.read().decode("utf-8", errors="ignore")
                raise RuntimeError(
                    f"Anthropic HTTP {exc.code} for model={self.config.model} url={url}: {error_body}"
                ) from exc
            except urllib.error.URLError as exc:
                raise RuntimeError(
                    f"Anthropic URL error for model={self.config.model} url={url}: {exc}"
                ) from exc

            text = "".join(
                block.get("text", "")
                for block in body.get("content", [])
                if isinstance(block, dict) and block.get("type") == "text"
            )

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
                f"Anthropic model returned non-parseable JSON after retries: {last_parse_error}. Preview: {last_text_preview}"
            ) from last_parse_error
        raise ValueError("Anthropic model returned empty content after retries.")
