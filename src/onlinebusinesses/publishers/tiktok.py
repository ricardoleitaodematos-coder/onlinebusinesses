from __future__ import annotations

from pathlib import Path

from ..http import HttpClient
from ..models import Insights
from .base import PublishError

INBOX_INIT = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"
MAX_SINGLE_CHUNK = 64 * 1024 * 1024


class TikTokDraftPublisher:
    """Envia o vídeo para os rascunhos do TikTok (scope video.upload).

    O endpoint de rascunhos não aceita legenda nem `is_aigc`: quem publica o rascunho na app põe a legenda
    e liga o rótulo de IA (a mensagem ao Ricardo leva ambos). Direct Post só depois da auditoria da app."""

    def __init__(self, http: HttpClient, token: str):
        self.http, self.token = http, token

    def publish(self, video: Path, caption: str, ai_label: bool, key: str) -> str:
        size = Path(video).stat().st_size
        if size > MAX_SINGLE_CHUNK:
            raise PublishError("vídeo acima de 64 MB: o envio em vários blocos não está implementado")
        try:
            init = self.http.post_json(INBOX_INIT, {"source_info": {
                "source": "FILE_UPLOAD", "video_size": size, "chunk_size": size, "total_chunk_count": 1}},
                headers={"Authorization": f"Bearer {self.token}"})
            error = init.get("error", {})
            if error.get("code", "ok") != "ok":
                raise PublishError(f"o TikTok recusou o pedido: {error.get('code')} {error.get('message', '')}".strip())
            data = init["data"]
            status = self.http.put_bytes(data["upload_url"], Path(video).read_bytes(), {
                "Content-Type": "video/mp4", "Content-Length": str(size),
                "Content-Range": f"bytes 0-{size - 1}/{size}"})
        except PublishError:
            raise
        except Exception as e:
            raise PublishError(f"falha ao enviar para o TikTok: {e}") from e
        if status != 201:
            raise PublishError(f"o envio ao TikTok terminou com o código {status}")
        return data["publish_id"]

    def insights(self, external_id: str) -> Insights:
        raise NotImplementedError("métricas do TikTok só depois da auditoria (/v2/video/query/, scope video.list)")
