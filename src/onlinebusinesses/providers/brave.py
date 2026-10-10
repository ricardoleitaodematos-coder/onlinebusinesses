"""Pesquisa web com a Brave Search API (https://api-dashboard.search.brave.com/app/documentation/web-search/get-started,
consultado a 2026-10-10): GET /res/v1/web/search, cabeçalho X-Subscription-Token, `freshness` com intervalo AAAA-MM-DDtoAAAA-MM-DD."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import urlparse

from ..http import HttpClient
from ..models import Source

ENDPOINT = "https://api.search.brave.com/res/v1/web/search"


def _parse_date(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class BraveSearch:
    """`tier` provisório 3: o `corroborate` recalcula-o pelo domínio canónico."""

    def __init__(self, http: HttpClient, api_key: str,
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.http, self.api_key, self.now = http, api_key, now

    def search(self, query: str, since: datetime) -> list[Source]:
        now = self.now()
        data = self.http.get_json(ENDPOINT, {"q": query, "count": 20, "freshness": f"{since:%Y-%m-%d}to{now:%Y-%m-%d}"},
                                  {"X-Subscription-Token": self.api_key, "Accept": "application/json"})
        out = []
        for r in (data.get("web") or {}).get("results") or []:
            url, title = r.get("url"), r.get("title")
            if not (url and title):
                continue
            domain = (urlparse(url).hostname or "").removeprefix("www.")
            out.append(Source(id=hashlib.sha1(url.encode()).hexdigest()[:8], url=url, domain=domain, title=title,
                              outlet=domain, published_at=_parse_date(r.get("page_age")) or now, tier=3))
        return out
