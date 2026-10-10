from __future__ import annotations

from typing import Mapping, Protocol

import httpx


class HttpClient(Protocol):
    def get_json(self, url: str, params: Mapping | None = None) -> dict: ...

    def post_json(self, url: str, payload: Mapping) -> dict: ...


class HttpxClient:
    def __init__(self, timeout: float = 30.0, transport: httpx.BaseTransport | None = None):
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def get_json(self, url: str, params: Mapping | None = None) -> dict:
        r = self._client.get(url, params=params)
        r.raise_for_status()
        return r.json()

    def post_json(self, url: str, payload: Mapping) -> dict:
        r = self._client.post(url, json=dict(payload))
        r.raise_for_status()
        return r.json()
