from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, Protocol, Sequence

from .config import today_lisbon
from .http import HttpClient
from .models import Proposal, Topic
from .store import Store

_ACTIONS = {"a": "accept", "r": "reject", "i": "improve"}
_TELEGRAM_LIMIT = 4096


@dataclass(frozen=True)
class TopicsChosen:
    day: date
    topic_ids: tuple[str, ...]


@dataclass(frozen=True)
class ProposalDecision:
    proposal_id: str
    action: Literal["accept", "reject", "improve"]
    revision: int | None = None  # versão da proposta na mensagem; None = formato antigo, não se verifica


@dataclass(frozen=True)
class Feedback:
    proposal_id: str
    text: str


Event = TopicsChosen | ProposalDecision | Feedback


class Channel(Protocol):
    def send_topics(self, day: date, topics: Sequence[Topic]) -> None: ...

    def send_proposal(self, p: Proposal, topic: Topic) -> None: ...

    def ask_feedback(self, proposal_id: str) -> None: ...

    def notify(self, text: str) -> None: ...

    def poll(self, now: datetime | None = None) -> list[Event]: ...


def stale_choice_text(day: str) -> str:
    return f"Esses temas são de {day}; espera pelos de hoje."


def render_topics(day: date, topics: Sequence[Topic]) -> str:
    lines = [f"Temas de {day.isoformat()}: escolhe 2.", ""]
    for n, t in enumerate(topics, 1):
        lines += [f"{n}. {t.title} [{t.category}]", f"   {t.summary}"]
        lines += [f"   • {s.url}" for s in t.sources[:3]]
        lines.append("")
    return "\n".join(lines).rstrip()


_ES_PREVIEW_CHARS = 400


def render_proposal(p: Proposal, topic: Topic, es: str | None = None) -> str:
    """`es` é o texto em espanhol (se existir): mostram-se as primeiras letras para o Ricardo o ver antes de aceitar."""
    urls = {s.id: s.url for s in topic.sources}
    lines = [f"Proposta {p.variant} — {topic.title}", "", p.script_pt, ""]
    if es:
        lines += ["Versão ES:", es[:_ES_PREVIEW_CHARS] + ("…" if len(es) > _ES_PREVIEW_CHARS else ""), ""]
    lines.append("Afirmações e fontes:")
    for c in p.claims:
        lines.append(f"- {c.text} ({', '.join(urls.get(i, '?') for i in c.source_ids)})")
    return "\n".join(lines)


class TelegramChannel:
    def __init__(self, http: HttpClient, token: str, chat_id: int, store: Store, picks: int = 2):
        self.http, self._token, self.chat_id, self.store, self.picks = http, token, chat_id, store, picks
        self._today: date | None = None

    def _url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self._token}/{method}"

    def _send(self, text: str, keyboard: list[list[dict]] | None = None) -> None:
        payload: dict = {"chat_id": self.chat_id, "text": text[:_TELEGRAM_LIMIT],
                         "link_preview_options": {"is_disabled": True}}
        if keyboard:
            payload["reply_markup"] = {"inline_keyboard": keyboard}
        self.http.post_json(self._url("sendMessage"), payload)

    @staticmethod
    def _topics_keyboard(day: date, count: int, selected: Sequence[int]) -> list[list[dict]]:
        numbers = [{"text": ("✅ " if n in selected else "") + str(n), "callback_data": f"t:{day.isoformat()}:{n}"}
                   for n in range(1, count + 1)]
        return [numbers, [{"text": "Confirmar", "callback_data": f"tc:{day.isoformat()}"}]]

    def send_topics(self, day: date, topics: Sequence[Topic]) -> None:
        self.store.set_selection(day, [])
        self._send(render_topics(day, topics), self._topics_keyboard(day, len(topics), []))

    def send_proposal(self, p: Proposal, topic: Topic) -> None:
        try:
            suffix = f":{self.store.revisions(p.id)}"  # botões de uma versão antiga deixam de valer
        except KeyError:
            suffix = ""
        row = [{"text": label, "callback_data": f"p:{p.id}:{code}{suffix}"}
               for label, code in (("Aceitar", "a"), ("Recusar", "r"), ("Melhorar", "i"))]
        self._send(render_proposal(p, topic, self.store.translation(p.id, "es")), [row])

    def ask_feedback(self, proposal_id: str) -> None:
        self.store.set_awaiting_feedback(proposal_id)
        self._send("O que queres que melhore? Responde com uma mensagem.")

    def notify(self, text: str) -> None:
        self._send(text)

    def poll(self, now: datetime | None = None) -> list[Event]:
        """`now` serve para recusar toques em temas de outro dia (sem `now` não se verifica)."""
        self._today = today_lisbon(now) if now is not None else None
        result = self.http.get_json(self._url("getUpdates"), {"offset": self.store.get_offset(), "timeout": 0})
        events: list[Event] = []
        for update in sorted(result.get("result", []), key=lambda u: u["update_id"]):
            if update["update_id"] < self.store.get_offset():
                continue
            self.store.set_offset(update["update_id"] + 1)
            events += self._handle(update)
        return events

    def _handle(self, update: dict) -> list[Event]:
        cq = update.get("callback_query")
        if cq:
            if cq["message"]["chat"]["id"] != self.chat_id:
                return []
            self.http.post_json(self._url("answerCallbackQuery"), {"callback_query_id": cq["id"]})
            return self._handle_callback(cq["data"], cq["message"]["message_id"])
        message = update.get("message")
        if message and message.get("chat", {}).get("id") == self.chat_id and message.get("text"):
            pending = self.store.awaiting_feedback()
            if pending:
                self.store.set_awaiting_feedback(None)
                return [Feedback(pending, message["text"])]
        return []

    def _stale_day(self, day_text: str) -> bool:
        if self._today is None or day_text == self._today.isoformat():
            return False
        self._send(stale_choice_text(day_text))
        return True

    def _handle_callback(self, data: str, message_id: int) -> list[Event]:
        kind, *rest = data.split(":")
        if kind == "p" and len(rest) in (2, 3) and rest[1] in _ACTIONS:
            if len(rest) == 3 and not rest[2].isdigit():
                return []
            revision = int(rest[2]) if len(rest) == 3 else None
            return [ProposalDecision(rest[0], _ACTIONS[rest[1]], revision)]  # type: ignore[arg-type]
        if kind in ("t", "tc") and self._stale_day(rest[0]):
            return []
        if kind == "t" and len(rest) == 2:
            day, n = date.fromisoformat(rest[0]), int(rest[1])
            chosen = [x for x in self.store.selection(day) if x != n]
            if len(chosen) == len(self.store.selection(day)):
                chosen.append(n)
            self.store.set_selection(day, chosen)
            count = len(self.store.topics(day))
            self.http.post_json(self._url("editMessageReplyMarkup"), {
                "chat_id": self.chat_id, "message_id": message_id,
                "reply_markup": {"inline_keyboard": self._topics_keyboard(day, count, chosen)}})
            return []
        if kind == "tc" and len(rest) == 1:
            day = date.fromisoformat(rest[0])
            chosen, topics = sorted(self.store.selection(day)), self.store.topics(day)
            if len(chosen) != self.picks:
                self._send(f"Escolhe exatamente {self.picks} temas (tens {len(chosen)}).")
                return []
            return [TopicsChosen(day, tuple(topics[n - 1].id for n in chosen))]
        return []
