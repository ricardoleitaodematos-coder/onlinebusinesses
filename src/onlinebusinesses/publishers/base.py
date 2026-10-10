from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ..models import Insights


class PublishError(Exception):
    pass


class Publisher(Protocol):
    def publish(self, video: Path, caption: str, ai_label: bool, key: str) -> str:
        """Devolve o id externo. `key` é a chave de idempotência da proposta (o Store evita duplicados)."""
        ...

    def insights(self, external_id: str) -> Insights: ...


class VideoHost(Protocol):
    def upload(self, path: Path) -> str:
        """Devolve um URL público do vídeo (o Instagram exige `video_url` público)."""
        ...
