from __future__ import annotations

import json
from typing import Mapping, Protocol


class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> str: ...


def parse_json_object(text: str) -> dict | None:
    """Extrai o primeiro objeto JSON de uma resposta do LLM; None se não houver."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


class AnthropicClient:
    """LLMClient sobre o SDK da Anthropic; o modelo vem sempre de fora (LLM_MODEL)."""

    def __init__(self, client, model: str, max_tokens: int = 16000):
        self._client, self._model, self._max_tokens = client, model, max_tokens

    def complete(self, system: str, user: str) -> str:
        response = self._client.messages.create(
            model=self._model, max_tokens=self._max_tokens, system=system,
            messages=[{"role": "user", "content": user}])
        return "".join(b.text for b in response.content if b.type == "text")


def build_llm(env: Mapping[str, str]) -> LLMClient:
    model, key = env.get("LLM_MODEL"), env.get("ANTHROPIC_API_KEY")
    if not model:
        raise ValueError("LLM_MODEL não definido")
    if not key:
        raise ValueError("ANTHROPIC_API_KEY não definido")
    import anthropic

    return AnthropicClient(anthropic.Anthropic(api_key=key), model)
