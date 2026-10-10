from datetime import date, datetime, timezone
from pathlib import Path

from onlinebusinesses.config import (canonical_domain, load_aliases, load_feeds, load_settings, load_sources, tier_of,
                                     today_lisbon)


def test_today_lisbon_at_midnight():
    assert today_lisbon(datetime(2026, 10, 10, 23, 30, tzinfo=timezone.utc)) == date(2026, 10, 11)


def test_load_settings_defaults():
    s = load_settings({})
    assert (s.topics_per_day, s.picks_per_day) == (5, 2)
    assert (s.require_accept_days, s.revision_limit) == (7, 3)
    assert s.tz == "Europe/Lisbon"
    assert s.telegram_chat_id is None


def test_load_settings_reads_env():
    s = load_settings({"TELEGRAM_CHAT_ID": "123", "LLM_MODEL": "m", "DB_PATH": "x.sqlite"})
    assert (s.telegram_chat_id, s.llm_model, s.db_path) == (123, "m", Path("x.sqlite"))


def test_load_feeds(tmp_path):
    f = tmp_path / "feeds.toml"
    f.write_text('[[feed]]\noutlet = "A"\nurl = "https://a.pt/rss"\n', encoding="utf-8")
    feeds = load_feeds(f)
    assert [(x.outlet, x.url) for x in feeds] == [("A", "https://a.pt/rss")]


def test_load_sources_and_tier_of_unknown_is_3(tmp_path):
    f = tmp_path / "sources.toml"
    f.write_text('[[source]]\ndomain = "bbc.co.uk"\ntier = 1\n', encoding="utf-8")
    tiers = load_sources(f)
    assert tier_of("bbc.co.uk", tiers) == 1
    assert tier_of("blog.example", tiers) == 3


def test_aliases_from_the_real_sources_file():
    aliases = load_aliases(Path("config/sources.toml"))
    assert aliases["bbc.com"] == "bbc.co.uk" and aliases["eur-lex.europa.eu"] == "europa.eu"
    assert canonical_domain("bbc.com", aliases) == "bbc.co.uk"
    assert canonical_domain("rtp.pt", aliases) == "rtp.pt"
