"""Fornecedores ainda por escolher (docs/setup-ricardo.md): falham com uma mensagem clara em vez de fingir."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Sequence

from .models import Source

_HINT = "ver docs/setup-ricardo.md"


class NullSearch:
    """Sem API de pesquisa web configurada: o pipeline segue só com os feeds RSS."""

    def search(self, query: str, since: datetime) -> list[Source]:
        return []


class UnconfiguredVoice:
    def synthesize(self, text: str, lang: str, out: Path) -> Path:
        raise RuntimeError(f"fornecedor de voz por configurar ({_HINT})")


class UnconfiguredVisuals:
    def render(self, prompts: Sequence[str], style: str, out_dir: Path) -> list[Path]:
        raise RuntimeError(f"fornecedor de visuais por configurar ({_HINT})")
