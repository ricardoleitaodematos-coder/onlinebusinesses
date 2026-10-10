from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from ..http import HttpClient
from ..models import Insights
from .base import PublishError, VideoHost

_METRICS = "views,likes,comments,shares,ig_reels_avg_watch_time"


class InstagramPublisher:
    """Instagram API com Instagram Login: contentor → estado → media_publish (docs oficiais, ver docs/compliance.md)."""

    def __init__(self, http: HttpClient, host: VideoHost, user_id: str, token: str,
                 base_url: str = "https://graph.instagram.com", sleep: Callable[[float], None] = time.sleep,
                 poll_interval: float = 60.0, max_polls: int = 5):
        self.http, self.host, self.user_id, self.token = http, host, user_id, token
        self.base, self.sleep, self.poll_interval, self.max_polls = base_url, sleep, poll_interval, max_polls

    def publish(self, video: Path, caption: str, ai_label: bool, key: str) -> str:
        try:
            container = self.http.post_json(f"{self.base}/{self.user_id}/media", {
                "media_type": "REELS", "video_url": self.host.upload(video), "caption": caption,
                "is_ai_generated": ai_label, "access_token": self.token})["id"]
            self._wait_until_finished(container)
            return self.http.post_json(f"{self.base}/{self.user_id}/media_publish",
                                       {"creation_id": container, "access_token": self.token})["id"]
        except PublishError:
            raise
        except Exception as e:
            raise PublishError(f"falha ao publicar no Instagram: {e}") from e

    def _wait_until_finished(self, container: str) -> None:
        for attempt in range(self.max_polls):
            status = self.http.get_json(f"{self.base}/{container}",
                                        {"fields": "status_code", "access_token": self.token})["status_code"]
            if status == "FINISHED":
                return
            if status in ("ERROR", "EXPIRED"):
                raise PublishError(f"o Instagram devolveu o estado {status}")
            if attempt < self.max_polls - 1:
                self.sleep(self.poll_interval)
        raise PublishError("o Instagram não terminou o processamento a tempo")

    def insights(self, external_id: str) -> Insights:
        data = self.http.get_json(f"{self.base}/{external_id}/insights",
                                  {"metric": _METRICS, "access_token": self.token})["data"]
        values = {m["name"]: m["values"][0]["value"] for m in data}
        return Insights(views=int(values.get("views", 0)), likes=int(values.get("likes", 0)),
                        comments=int(values.get("comments", 0)), shares=int(values.get("shares", 0)),
                        avg_watch_s=float(values.get("ig_reels_avg_watch_time", 0)) / 1000)
