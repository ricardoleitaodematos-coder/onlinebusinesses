from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Callable, Mapping, Protocol, Sequence
from urllib.parse import urlparse

import feedparser

from .config import FeedConfig, canonical_domain, tier_of
from .llm import LLMClient, parse_json_object
from .models import Source, Topic

HttpGet = Callable[[str], str]
MAX_TRUSTED_TIER = 2
_STOP = {"que", "com", "para", "por", "uma", "dos", "das", "the", "and", "for", "from", "with", "pelo", "pela"}
_CATEGORIES = {"ai", "geopolitics", "national", "other"}


class SearchProvider(Protocol):
    def search(self, query: str, since: datetime) -> list[Source]: ...


def _domain(url: str) -> str:
    host = urlparse(url).hostname or ""
    return host[4:] if host.startswith("www.") else host


def _source_id(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:8]


def _canonical(domain: str, tiers: Mapping[str, int], aliases: Mapping[str, str]) -> tuple[str, int]:
    canonical = canonical_domain(domain, aliases)
    return canonical, tier_of(domain if domain in tiers else canonical, tiers)


def fetch_items(feeds: Sequence[FeedConfig], tiers: Mapping[str, int], http: HttpGet, now: datetime,
                max_age_hours: int = 36, aliases: Mapping[str, str] | None = None) -> list[Source]:
    aliases = aliases or {}
    items: list[Source] = []
    oldest = now - timedelta(hours=max_age_hours)
    for feed in feeds:
        try:
            parsed = feedparser.parse(http(feed.url))
        except Exception:
            continue
        for e in parsed.entries:
            link, title, stamp = e.get("link"), e.get("title"), e.get("published_parsed")
            if not (link and title and stamp):
                continue
            published = datetime(*stamp[:6], tzinfo=timezone.utc)
            if published < oldest:
                continue
            domain, tier = _canonical(_domain(link), tiers, aliases)
            items.append(Source(id=_source_id(link), url=link, domain=domain, title=title, outlet=feed.outlet,
                                published_at=published, tier=tier))  # type: ignore[arg-type]
    return items


def _tokens(title: str) -> set[str]:
    plain = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower()
    return {w for w in re.findall(r"[a-z0-9]+", plain) if len(w) > 2 and w not in _STOP}


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def _trusted_domains(sources: Sequence[Source]) -> set[str]:
    return {s.domain for s in sources if s.tier <= MAX_TRUSTED_TIER}


def cluster_topics(items: Sequence[Source], salt: str = "") -> list[Topic]:
    """Agrupa notícias por título. `salt` (o dia) entra no id: os mesmos artigos noutro dia são outro tema."""
    trusted = [i for i in items if i.tier <= MAX_TRUSTED_TIER]
    groups: list[tuple[set[str], list[Source]]] = []
    for item in trusted:
        toks = _tokens(item.title)
        best = max(groups, key=lambda g: _jaccard(toks, g[0]), default=None)
        if best is not None and _jaccard(toks, best[0]) >= 0.5:
            best[1].append(item)
        else:
            groups.append((toks, [item]))
    topics = []
    for _, members in groups:
        domains = _trusted_domains(members)
        if len(domains) < 2:
            continue
        key = "|".join(sorted(m.id for m in members))
        tid = "t" + hashlib.sha1(f"{salt}#{key}".encode() if salt else key.encode()).hexdigest()[:7]
        topics.append(Topic(id=tid, title=members[0].title, summary="Fontes: " + ", ".join(sorted(domains)),
                            sources=tuple(members), category="other", travels=False, context=""))
    return topics


def corroborate(topic: Topic, search: SearchProvider, tiers: Mapping[str, int], now: datetime,
                aliases: Mapping[str, str] | None = None) -> Topic:
    aliases = aliases or {}
    try:
        found = search.search(topic.title, now - timedelta(hours=36))
    except Exception:
        return topic
    known = {s.url for s in topic.sources}
    extra = []
    for s in found:
        domain, tier = _canonical(s.domain, tiers, aliases)
        s = replace(s, domain=domain, tier=tier)  # type: ignore[arg-type]
        if s.tier <= MAX_TRUSTED_TIER and s.url not in known:
            known.add(s.url)
            extra.append(s)
    return replace(topic, sources=topic.sources + tuple(extra)) if extra else topic


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        self._skip += tag in ("script", "style")

    def handle_endtag(self, tag):
        self._skip -= tag in ("script", "style") and self._skip > 0

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.parts.append(data.strip())


def add_context(topic: Topic, http: HttpGet, max_chars: int = 4000) -> Topic:
    texts, seen = [], set()
    for s in topic.sources:
        if s.tier > MAX_TRUSTED_TIER or s.domain in seen:
            continue
        seen.add(s.domain)
        try:
            parser = _Text()
            parser.feed(http(s.url))
            texts.append(" ".join(parser.parts))
        except Exception:
            continue
        if len(texts) == 2:
            break
    return replace(topic, context="\n".join(texts)[:max_chars])


def classify_topics(topics: Sequence[Topic], llm: LLMClient) -> list[Topic]:
    system = ('Classifica o tema de notícia. Responde só com JSON: {"category": "ai|geopolitics|national|other", '
              '"travels": true se o tema interessa também ao Brasil e a Espanha, false se é só nacional}.')
    out = []
    for t in topics:
        try:
            data = parse_json_object(llm.complete(system, f"{t.title}\n{t.summary}\n{t.context[:500]}")) or {}
        except Exception:
            data = {}
        category = data.get("category") if data.get("category") in _CATEGORIES else "other"
        travels = data.get("travels") if isinstance(data.get("travels"), bool) else False
        out.append(replace(t, category=category, travels=travels))
    return out


def rank_topics(topics: Sequence[Topic], n: int = 5) -> list[Topic]:
    def key(t: Topic):
        return (-len(_trusted_domains(t.sources)), -max(s.published_at for s in t.sources).timestamp())

    return sorted(topics, key=key)[:n]
