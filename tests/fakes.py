from __future__ import annotations


class FakeLLM:
    """Devolve respostas por ordem; repete a última se acabarem."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        i = min(len(self.calls) - 1, len(self.responses) - 1)
        r = self.responses[i]
        if isinstance(r, Exception):
            raise r
        return r


class FakeSearch:
    def __init__(self, results=(), error: Exception | None = None):
        self.results = list(results)
        self.error = error
        self.queries: list[str] = []

    def search(self, query, since):
        self.queries.append(query)
        if self.error:
            raise self.error
        return list(self.results)


class FakeHttp:
    """HttpClient falso: guarda os POST e devolve updates do Telegram pré-carregados."""

    def __init__(self, updates=()):
        self.updates = list(updates)
        self.posts: list[tuple[str, dict]] = []
        self.gets: list[tuple[str, dict | None]] = []

    def get_json(self, url, params=None):
        self.gets.append((url, params))
        return {"ok": True, "result": list(self.updates)}

    def post_json(self, url, payload):
        self.posts.append((url, dict(payload)))
        return {"ok": True, "result": {"message_id": len(self.posts)}}

    def sent(self, method):
        return [p for u, p in self.posts if u.endswith("/" + method)]


class FakeApi:
    """HttpClient falso com rotas: {"POST /media": resposta | [respostas] | Exception}.

    A rota casa por método e sufixo do URL; uma lista é consumida por ordem (a última repete-se)."""

    def __init__(self, routes):
        self.routes = dict(routes)
        self.calls: list[tuple[str, str, object, dict | None]] = []

    def _answer(self, method, url, body, headers):
        self.calls.append((method, url, body, headers))
        for key, value in self.routes.items():
            m, suffix = key.split(" ", 1)
            if m == method and url.split("?")[0].endswith(suffix):
                if isinstance(value, list):
                    value = value.pop(0) if len(value) > 1 else value[0]
                if isinstance(value, Exception):
                    raise value
                return value
        raise AssertionError(f"rota inesperada: {method} {url}")

    def get_json(self, url, params=None, headers=None):
        return self._answer("GET", url, params, headers)

    def post_json(self, url, payload, headers=None):
        return self._answer("POST", url, payload, headers)

    def put_bytes(self, url, data, headers):
        return self._answer("PUT", url, data, headers)
