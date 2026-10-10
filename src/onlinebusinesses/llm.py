from __future__ import annotations

import json
from typing import Protocol


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
