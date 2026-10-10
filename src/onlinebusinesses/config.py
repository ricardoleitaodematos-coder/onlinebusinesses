from __future__ import annotations

import tomllib
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Mapping
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Settings:
    db_path: Path
    feeds_path: Path
    sources_path: Path
    out_dir: Path
    tz: str
    require_accept_days: int
    publish_hold_minutes: int
    revision_limit: int
    topics_per_day: int
    picks_per_day: int
    llm_model: str
    telegram_chat_id: int | None


@dataclass(frozen=True)
class FeedConfig:
    outlet: str
    url: str


def load_settings(env: Mapping[str, str]) -> Settings:
    chat = env.get("TELEGRAM_CHAT_ID")
    return Settings(
        db_path=Path(env.get("DB_PATH", "data/onlinebusinesses.sqlite")),
        feeds_path=Path(env.get("FEEDS_PATH", "config/feeds.toml")),
        sources_path=Path(env.get("SOURCES_PATH", "config/sources.toml")),
        out_dir=Path(env.get("OUT_DIR", "out")),
        tz=env.get("TZ_NAME", "Europe/Lisbon"),
        require_accept_days=int(env.get("REQUIRE_ACCEPT_DAYS", "7")),
        publish_hold_minutes=int(env.get("PUBLISH_HOLD_MINUTES", "120")),
        revision_limit=int(env.get("REVISION_LIMIT", "3")),
        topics_per_day=int(env.get("TOPICS_PER_DAY", "5")),
        picks_per_day=int(env.get("PICKS_PER_DAY", "2")),
        llm_model=env.get("LLM_MODEL", ""),
        telegram_chat_id=int(chat) if chat else None,
    )


def load_feeds(path: Path) -> list[FeedConfig]:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    return [FeedConfig(outlet=f["outlet"], url=f["url"]) for f in data.get("feed", [])]


def load_sources(path: Path) -> dict[str, int]:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    return {s["domain"]: int(s["tier"]) for s in data.get("source", [])}


def tier_of(domain: str, tiers: Mapping[str, int]) -> int:
    return tiers.get(domain, 3)


def today_lisbon(now: datetime) -> date:
    return now.astimezone(ZoneInfo("Europe/Lisbon")).date()


def load_aliases(path: Path) -> dict[str, str]:
    """Domínios do mesmo órgão (`same_as`): contam como uma só fonte."""
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    return {s["domain"]: s["same_as"] for s in data.get("source", []) if s.get("same_as")}


def canonical_domain(domain: str, aliases: Mapping[str, str]) -> str:
    return aliases.get(domain, domain)
