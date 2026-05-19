from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LLMMessage:
    role: str
    content: str


class LLMProvider:
    def create_json(self, messages: list[LLMMessage], schema: dict) -> dict:
        raise NotImplementedError


def extract_json_object(text: str) -> str:
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
