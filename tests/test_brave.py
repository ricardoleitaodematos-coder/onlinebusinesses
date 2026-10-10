from datetime import datetime, timedelta, timezone

import pytest
from fakes import FakeApi
from onlinebusinesses.http import HttpError
from onlinebusinesses.providers.brave import BraveSearch

NOW = datetime(2026, 10, 10, 8, 0, tzinfo=timezone.utc)
URL = "https://api.search.brave.com/res/v1/web/search"


def test_search_maps_results_and_sends_token_header():
    api = FakeApi({"GET /web/search": {"web": {"results": [
        {"title": "A", "url": "https://www.publico.pt/x", "page_age": "2026-10-10T06:30:00"},
        {"title": "B", "url": "https://bbc.com/y"},
        {"title": "", "url": "https://z.com/"}]}}})
    out = BraveSearch(api, "KEY", now=lambda: NOW).search("tema", NOW - timedelta(hours=36))
    assert [(s.title, s.domain, s.tier) for s in out] == [("A", "publico.pt", 3), ("B", "bbc.com", 3)]
    assert out[0].published_at == datetime(2026, 10, 10, 6, 30, tzinfo=timezone.utc)
    assert out[1].published_at == NOW  # sem data: usa o momento da pesquisa
    assert out[0].id != out[1].id
    _, url, params, headers = api.calls[0]
    assert url == URL and headers["X-Subscription-Token"] == "KEY"
    assert params["q"] == "tema" and params["freshness"] == "2026-10-08to2026-10-10"


def test_error_propagates_without_key():
    api = FakeApi({"GET /web/search": HttpError(429, "GET", "api.search.brave.com")})
    with pytest.raises(HttpError) as e:
        BraveSearch(api, "KEY").search("t", NOW)
    assert "KEY" not in str(e.value)


def test_empty_response():
    assert BraveSearch(FakeApi({"GET /web/search": {}}), "K").search("t", NOW) == []
