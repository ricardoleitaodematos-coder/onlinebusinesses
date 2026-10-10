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
