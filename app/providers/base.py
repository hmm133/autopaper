from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LLMMessage:
    role: str
    content: str


class LLMProvider:
    def create_json(self, messages: list[LLMMessage], schema: dict) -> dict:
        raise NotImplementedError
