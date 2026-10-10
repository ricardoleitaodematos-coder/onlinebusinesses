from __future__ import annotations

from typing import Callable, Mapping, Protocol
from urllib.parse import urlparse

import httpx


class HttpError(Exception):
    """Erro HTTP sem URL: só estado, método e anfitrião (o URL pode levar tokens no caminho ou na query)."""

    def __init__(self, status: int | None, method: str, host: str):
        self.status, self.method, self.host = status, method, host
        super().__init__(f"HTTP {status} em {method} {host}" if status is not None
                         else f"falha de rede em {method} {host}")


class HttpClient(Protocol):
    def get_json(self, url: str, params: Mapping | None = None, headers: Mapping | None = None) -> dict: ...

    def post_json(self, url: str, payload: Mapping, headers: Mapping | None = None) -> dict: ...

    def put_bytes(self, url: str, data: bytes, headers: Mapping) -> int: ...


class HttpxClient:
    """Cliente HTTP real. Todos os erros saem como HttpError, sem o URL (que pode levar tokens)."""

    def __init__(self, timeout: float = 30.0, transport: httpx.BaseTransport | None = None):
        self._client = httpx.Client(timeout=timeout, transport=transport)

    @staticmethod
    def _call(method: str, url: str, send: Callable[[], httpx.Response], check: bool = True) -> httpx.Response:
        host = urlparse(url).hostname or "?"
        try:
            r = send()
        except httpx.HTTPError:
            raise HttpError(None, method, host) from None
        if check and r.is_error:
            raise HttpError(r.status_code, method, host)
        return r

    def get_json(self, url: str, params: Mapping | None = None, headers: Mapping | None = None) -> dict:
        return self._call("GET", url, lambda: self._client.get(url, params=params, headers=headers)).json()

    def post_json(self, url: str, payload: Mapping, headers: Mapping | None = None) -> dict:
        return self._call("POST", url, lambda: self._client.post(url, json=dict(payload), headers=headers)).json()

    def put_bytes(self, url: str, data: bytes, headers: Mapping) -> int:
        return self._call("PUT", url, lambda: self._client.put(url, content=data, headers=dict(headers)),
                          check=False).status_code
