from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence

import httpx

from .brief import TelegramChannel
from .config import load_aliases, load_settings, load_sources, today_lisbon
from .gates import load_blocklist
from .http import HttpxClient
from .llm import build_llm
from .metrics import collect_insights, weekly_report
from .pipeline import Pipeline
from .publishers.tiktok import TikTokDraftPublisher
from .store import Store
from .unconfigured import NullSearch, UnconfiguredVisuals, UnconfiguredVoice

COMMANDS = ("research", "poll", "publish", "report")
SECRET_VARS = ("TELEGRAM_BOT_TOKEN", "ANTHROPIC_API_KEY", "TIKTOK_ACCESS_TOKEN", "INSTAGRAM_ACCESS_TOKEN")


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
                    settings.out_dir / "work", aliases=load_aliases(settings.sources_path))


def redact(text: str, env: Mapping[str, str]) -> str:
    for name in SECRET_VARS:
        if value := env.get(name):
            text = text.replace(value, "***")
    return text


def main(argv: Sequence[str], env: Mapping[str, str], factory: Callable[[Mapping[str, str]], Pipeline] = build_pipeline,
         now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> int:
    usage = f"uso: python -m onlinebusinesses {{{'|'.join(COMMANDS)}}} (report aceita uma data AAAA-MM-DD)"
    if not argv or argv[0] not in COMMANDS or len(argv) > (2 if argv[0] == "report" else 1):
        print(usage, file=sys.stderr)
        return 2
    try:
        report_start = date.fromisoformat(argv[1]) if len(argv) == 2 else None
    except ValueError:
        print(usage, file=sys.stderr)
        return 2
    try:
        return _run(argv[0], report_start, env, factory, now)
    except ConfigError as e:
        print(redact(f"configuração em falta: {e}", env), file=sys.stderr)
        return 1
    except Exception as e:  # nunca deixar sair um traceback com URLs ou tokens
        print(redact(f"erro em {argv[0]}: {type(e).__name__}: {e}", env), file=sys.stderr)
        return 1


def _run(command: str, report_start: date | None, env: Mapping[str, str],
         factory: Callable[[Mapping[str, str]], Pipeline], now: Callable[[], datetime]) -> int:
    pipeline = factory(env)
    if command == "report":
        collect_insights(pipeline.store, pipeline.publishers)
        first = pipeline.store.first_day()
        start = report_start or (first + timedelta(days=pipeline.settings.require_accept_days) if first
                                 else today_lisbon(now()))
        print(weekly_report(pipeline.store, start))
        return 0
    stage = {"research": pipeline.stage_research, "poll": pipeline.stage_poll, "publish": pipeline.stage_publish}
    stage[command](now())
    return 0
