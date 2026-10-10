from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, Sequence

from .models import Insights, Proposal, Topic

Status = Literal["draft", "gated", "approved", "rejected", "revising", "published", "expired"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS topics (day TEXT, id TEXT, json TEXT, PRIMARY KEY (day, id));
CREATE TABLE IF NOT EXISTS choices (day TEXT PRIMARY KEY, ids TEXT);
CREATE TABLE IF NOT EXISTS proposals (
  id TEXT PRIMARY KEY, topic_id TEXT, variant TEXT, json TEXT,
  status TEXT NOT NULL DEFAULT 'draft', reasons TEXT NOT NULL DEFAULT '[]',
  revisions INTEGER NOT NULL DEFAULT 0, status_at TEXT);
CREATE TABLE IF NOT EXISTS publications (
  proposal_id TEXT, platform TEXT, external_id TEXT, published_on TEXT, PRIMARY KEY (proposal_id, platform));
CREATE TABLE IF NOT EXISTS claims (
  proposal_id TEXT, platform TEXT, claimed_at TEXT, PRIMARY KEY (proposal_id, platform));
CREATE TABLE IF NOT EXISTS decisions (proposal_id TEXT, action TEXT, day TEXT);
CREATE TABLE IF NOT EXISTS insights (
  proposal_id TEXT, platform TEXT, json TEXT, PRIMARY KEY (proposal_id, platform));
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


def _ts(at: datetime) -> str:
    """UTC, largura fixa: as comparações de texto no SQLite ficam corretas."""
    return at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)

    def _conn(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _run(self, sql: str, params: Sequence = ()) -> list[sqlite3.Row]:
        with self._conn() as conn:
            return conn.execute(sql, params).fetchall()

    def _exec(self, sql: str, params: Sequence = ()) -> int:
        with self._conn() as conn:
            return conn.execute(sql, params).rowcount

    def init(self) -> None:
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    # temas e escolha
    def save_topics(self, day: date, topics: Sequence[Topic]) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM topics WHERE day = ?", (day.isoformat(),))
            conn.executemany("INSERT INTO topics VALUES (?, ?, ?)",
                             [(day.isoformat(), t.id, t.to_json()) for t in topics])

    def topics(self, day: date) -> list[Topic]:
        rows = self._run("SELECT json FROM topics WHERE day = ? ORDER BY rowid", (day.isoformat(),))
        return [Topic.from_json(r["json"]) for r in rows]

    def save_choice(self, day: date, topic_ids: Sequence[str]) -> None:
        self._run("INSERT OR REPLACE INTO choices VALUES (?, ?)", (day.isoformat(), json.dumps(list(topic_ids))))

    def choice(self, day: date) -> list[str]:
        rows = self._run("SELECT ids FROM choices WHERE day = ?", (day.isoformat(),))
        return json.loads(rows[0]["ids"]) if rows else []

    # propostas
    def save_proposals(self, props: Sequence[Proposal]) -> None:
        with self._conn() as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO proposals (id, topic_id, variant, json) VALUES (?, ?, ?, ?)",
                [(p.id, p.topic_id, p.variant, p.to_json()) for p in props])

    def topic(self, topic_id: str) -> Topic:
        rows = self._run("SELECT json FROM topics WHERE id = ? ORDER BY day DESC LIMIT 1", (topic_id,))
        if not rows:
            raise KeyError(topic_id)
        return Topic.from_json(rows[0]["json"])

    def topic_day(self, topic_id: str) -> date:
        return date.fromisoformat(self._one("SELECT MAX(day) FROM topics WHERE id = ? HAVING COUNT(*) > 0", topic_id))

    def proposal(self, proposal_id: str) -> Proposal:
        return Proposal.from_json(self._one("SELECT json FROM proposals WHERE id = ?", proposal_id))

    def proposals_by_status(self, status: Status) -> list[Proposal]:
        rows = self._run("SELECT json FROM proposals WHERE status = ? ORDER BY rowid", (status,))
        return [Proposal.from_json(r["json"]) for r in rows]

    def proposals_for(self, topic_id: str) -> list[Proposal]:
        rows = self._run("SELECT json FROM proposals WHERE topic_id = ? ORDER BY variant", (topic_id,))
        return [Proposal.from_json(r["json"]) for r in rows]

    def replace_proposal(self, p: Proposal) -> None:
        self._run("UPDATE proposals SET json = ? WHERE id = ?", (p.to_json(), p.id))

    def set_status(self, proposal_id: str, status: Status, reasons: Sequence[str] = (),
                   at: datetime | None = None) -> None:
        self._run("UPDATE proposals SET status = ?, reasons = ?, status_at = ? WHERE id = ?",
                  (status, json.dumps(list(reasons)), _ts(at or datetime.now(timezone.utc)), proposal_id))

    def status_at(self, proposal_id: str) -> datetime | None:
        v = self._one("SELECT status_at FROM proposals WHERE id = ?", proposal_id)
        return datetime.fromisoformat(v) if v else None

    def status(self, proposal_id: str) -> Status:
        return self._one("SELECT status FROM proposals WHERE id = ?", proposal_id)

    def reasons(self, proposal_id: str) -> list[str]:
        return json.loads(self._one("SELECT reasons FROM proposals WHERE id = ?", proposal_id))

    def bump_revision(self, proposal_id: str) -> int:
        self._run("UPDATE proposals SET revisions = revisions + 1 WHERE id = ?", (proposal_id,))
        return self._one("SELECT revisions FROM proposals WHERE id = ?", proposal_id)

    def _one(self, sql: str, key: str):
        rows = self._run(sql, (key,))
        if not rows:
            raise KeyError(key)
        return rows[0][0]

    # publicações
    def record_publication(self, proposal_id: str, platform: str, external_id: str, day: date | None = None) -> None:
        self._run("INSERT OR IGNORE INTO publications VALUES (?, ?, ?, ?)",
                  (proposal_id, platform, external_id, day.isoformat() if day else None))

    def first_publication_day(self) -> date | None:
        """Dia da primeira publicação: começa aqui o período de aceitação obrigatória."""
        v = self._run("SELECT MIN(published_on) FROM publications WHERE published_on IS NOT NULL")[0][0]
        return date.fromisoformat(v) if v else None

    CLAIM_TTL = timedelta(minutes=60)

    def claim_publication(self, proposal_id: str, platform: str, now: datetime) -> bool:
        """Reserva atómica antes do upload: só uma execução publica cada proposta+plataforma. Uma reserva parada há
        mais de CLAIM_TTL sem publicação (processo morto a meio) pode ser retomada."""
        not_published = "NOT EXISTS (SELECT 1 FROM publications WHERE proposal_id = ? AND platform = ?)"
        key = (proposal_id, platform)
        if self._exec(f"INSERT OR IGNORE INTO claims SELECT ?, ?, ? WHERE {not_published}", (*key, _ts(now), *key)):
            return True
        return bool(self._exec(f"UPDATE claims SET claimed_at = ? WHERE proposal_id = ? AND platform = ? "
                               f"AND claimed_at < ? AND {not_published}",
                               (_ts(now), *key, _ts(now - self.CLAIM_TTL), *key)))

    def release_claim(self, proposal_id: str, platform: str) -> None:
        self._run("DELETE FROM claims WHERE proposal_id = ? AND platform = ?", (proposal_id, platform))

    def all_publications(self) -> list[tuple[str, str, str]]:
        return [(r[0], r[1], r[2]) for r in self._run("SELECT proposal_id, platform, external_id FROM publications")]

    def publications_between(self, start: date, end: date) -> list[tuple[str, str, str, date]]:
        rows = self._run("SELECT proposal_id, platform, external_id, published_on FROM publications "
                         "WHERE published_on BETWEEN ? AND ? ORDER BY published_on, rowid",
                         (start.isoformat(), end.isoformat()))
        return [(r[0], r[1], r[2], date.fromisoformat(r[3])) for r in rows]

    # decisões do Ricardo e métricas
    def record_decision(self, proposal_id: str, action: str, day: date) -> None:
        self._run("INSERT INTO decisions VALUES (?, ?, ?)", (proposal_id, action, day.isoformat()))

    def decisions_between(self, start: date, end: date) -> int:
        return self._run("SELECT COUNT(*) FROM decisions WHERE day BETWEEN ? AND ?",
                         (start.isoformat(), end.isoformat()))[0][0]

    def save_insights(self, proposal_id: str, platform: str, ins: Insights) -> None:
        self._run("INSERT OR REPLACE INTO insights VALUES (?, ?, ?)", (proposal_id, platform, ins.to_json()))

    def insights_for(self, proposal_id: str) -> list[tuple[str, Insights]]:
        rows = self._run("SELECT platform, json FROM insights WHERE proposal_id = ? ORDER BY platform", (proposal_id,))
        return [(r[0], Insights.from_json(r[1])) for r in rows]

    def publication(self, proposal_id: str, platform: str) -> str | None:
        rows = self._run("SELECT external_id FROM publications WHERE proposal_id = ? AND platform = ?",
                         (proposal_id, platform))
        return rows[0][0] if rows else None

    # meta
    def _get_meta(self, key: str) -> str | None:
        rows = self._run("SELECT value FROM meta WHERE key = ?", (key,))
        return rows[0][0] if rows else None

    def _set_meta(self, key: str, value: str | None) -> None:
        if value is None:
            self._run("DELETE FROM meta WHERE key = ?", (key,))
        else:
            self._run("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, value))

    def first_day(self) -> date | None:
        v = self._get_meta("first_day")
        return date.fromisoformat(v) if v else None

    def set_first_day(self, day: date) -> None:
        self._run("INSERT OR IGNORE INTO meta VALUES ('first_day', ?)", (day.isoformat(),))

    def get_offset(self) -> int:
        return int(self._get_meta("offset") or 0)

    def set_offset(self, n: int) -> None:
        self._set_meta("offset", str(n))

    def set_awaiting_feedback(self, proposal_id: str | None) -> None:
        self._set_meta("awaiting_feedback", proposal_id)

    def awaiting_feedback(self) -> str | None:
        return self._get_meta("awaiting_feedback")

    def selection(self, day: date) -> list[int]:
        return json.loads(self._get_meta(f"selection:{day.isoformat()}") or "[]")

    def set_selection(self, day: date, numbers: Sequence[int]) -> None:
        self._set_meta(f"selection:{day.isoformat()}", json.dumps(list(numbers)))
