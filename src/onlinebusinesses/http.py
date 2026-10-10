from __future__ import annotations

from typing import Mapping, Protocol

import httpx


class HttpClient(Protocol):
    def get_json(self, url: str, params: Mapping | None = None, headers: Mapping | None = None) -> dict: ...

    def post_json(self, url: str, payload: Mapping, headers: Mapping | None = None) -> dict: ...

    def put_bytes(self, url: str, data: bytes, headers: Mapping) -> int: ...


class HttpxClient:
    def __init__(self, timeout: float = 30.0, transport: httpx.BaseTransport | None = None):
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def get_json(self, url: str, params: Mapping | None = None, headers: Mapping | None = None) -> dict:
        r = self._client.get(url, params=params, headers=headers)
        r.raise_for_status()
        return r.json()

    def post_json(self, url: str, payload: Mapping, headers: Mapping | None = None) -> dict:
        r = self._client.post(url, json=dict(payload), headers=headers)
        r.raise_for_status()
        return r.json()

    def put_bytes(self, url: str, data: bytes, headers: Mapping) -> int:
        return self._client.put(url, content=data, headers=dict(headers)).status_code
