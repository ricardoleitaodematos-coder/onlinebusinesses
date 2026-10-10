from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence

import httpx

from .brief import TelegramChannel
from .config import load_settings, load_sources
from .gates import load_blocklist
from .http import HttpxClient
from .llm import build_llm
from .pipeline import Pipeline
from .publishers.tiktok import TikTokDraftPublisher
from .store import Store
from .unconfigured import NullSearch, UnconfiguredVisuals, UnconfiguredVoice

COMMANDS = ("research", "poll", "publish")


class ConfigError(Exception):
    pass


def _get_text(url: str) -> str:
    response = httpx.get(url, timeout=30, follow_redirects=True, headers={"User-Agent": "onlinebusinesses/0.0.1"})
    response.raise_for_status()
    return response.text


def build_pipeline(env: Mapping[str, str]) -> Pipeline:
    settings = load_settings(env)
    token = env.get("TELEGRAM_BOT_TOKEN")
    if not token or settings.telegram_chat_id is None:
        raise ConfigError("faltam TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID (ver docs/setup-ricardo.md)")
    try:
        llm = build_llm(env)
    except ValueError as e:
        raise ConfigError(str(e)) from e
    store = Store(settings.db_path)
    store.init()
    http = HttpxClient()
    publishers = {}
    if env.get("TIKTOK_ACCESS_TOKEN"):
        publishers["tiktok"] = TikTokDraftPublisher(http, env["TIKTOK_ACCESS_TOKEN"])
    # Instagram: precisa de um VideoHost real (URL público); por configurar, por isso não se regista aqui.
    return Pipeline(store, TelegramChannel(http, token, settings.telegram_chat_id, store, settings.picks_per_day),
                    llm, NullSearch(), UnconfiguredVoice(), UnconfiguredVisuals(), publishers, settings, _get_text,
                    load_blocklist(Path("config/blocklist.toml")), load_sources(settings.sources_path),
                    settings.out_dir / "work")


def main(argv: Sequence[str], env: Mapping[str, str], factory: Callable[[Mapping[str, str]], Pipeline] = build_pipeline,
         now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> int:
    if len(argv) != 1 or argv[0] not in COMMANDS:
        print(f"uso: python -m onlinebusinesses {{{'|'.join(COMMANDS)}}}", file=sys.stderr)
        return 2
    try:
        pipeline = factory(env)
    except ConfigError as e:
        print(f"configuração em falta: {e}", file=sys.stderr)
        return 1
    stage = {"research": pipeline.stage_research, "poll": pipeline.stage_poll, "publish": pipeline.stage_publish}
    stage[argv[0]](now())
    return 0
