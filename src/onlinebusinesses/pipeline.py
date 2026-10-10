from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Mapping, Sequence

from .brief import Channel, Feedback, ProposalDecision, TopicsChosen
from .config import Settings, load_feeds, today_lisbon
from .gates import blocked_words, copyright_gate, run_gates
from .llm import LLMClient
from .media import Visuals, Voice, build_video
from .models import Proposal, Topic
from .proposals import generate_proposals, revise_proposal
from .publishers.base import Publisher
from .research import (HttpGet, SearchProvider, add_context, classify_topics, cluster_topics, corroborate,
                       fetch_items, rank_topics)
from .store import Store

# Fase 0: só se produz e publica o vídeo pt-PT. PT-BR e ES (build_video já os suporta) ficam à espera da decisão
# do Ricardo sobre as contas por língua (spec, decisões em aberto).
PUBLISH_LANGUAGES = ("pt-PT",)


def _hook(script: str) -> str:
    """Primeira frase do guião: é o gancho da legenda (nunca o título cru da notícia)."""
    text = " ".join(script.split())
    return re.split(r"(?<=[.!?…])\s+", text, maxsplit=1)[0]


def caption_for(p: Proposal, topic: Topic) -> str:
    domains = ", ".join(sorted({s.domain for s in topic.sources if s.tier <= 2}))
    return f"{_hook(p.script_pt)}\n\nConteúdo satírico gerado com IA. Fontes: {domains}"


class Pipeline:
    def __init__(self, store: Store, channel: Channel, llm: LLMClient, search: SearchProvider, voice: Voice | None,
                 visuals: Visuals | None, publishers: Mapping[str, Publisher], settings: Settings, http: HttpGet,
                 blocklist: Mapping[str, Sequence[str]], tiers: Mapping[str, int], workdir: Path,
                 builder: Callable = build_video, aliases: Mapping[str, str] | None = None):
        self.store, self.channel, self.llm, self.search = store, channel, llm, search
        self.voice, self.visuals, self.publishers, self.settings = voice, visuals, publishers, settings
        self.http, self.blocklist, self.tiers, self.workdir, self.builder = http, blocklist, tiers, Path(workdir), builder
        self.aliases = dict(aliases or {})

    # --- pesquisa -----------------------------------------------------------------------------------------------
    def stage_research(self, now: datetime) -> list[Topic]:
        day = today_lisbon(now)
        self.store.set_first_day(day)
        if existing := self.store.topics(day):
            return existing
        items = fetch_items(load_feeds(self.settings.feeds_path), self.tiers, self.http, now, aliases=self.aliases)
        topics = [corroborate(t, self.search, self.tiers, now, aliases=self.aliases)
                  for t in cluster_topics(items, salt=day.isoformat())]
        safe = [t for t in topics if not self._sensitive(t)]
        top = [add_context(t, self.http) for t in rank_topics(safe, self.settings.topics_per_day)]
        clean = [t for t in top if not self._sensitive(t)]
        if discarded := len(topics) - len(safe) + len(top) - len(clean):
            self.channel.notify(f"Descartei {discarded} tema(s) com palavras vetadas (mortes, tragédias, menores…).")
        top = classify_topics(clean, self.llm)
        if not top:
            self.channel.notify("Hoje não encontrei temas com duas fontes fiáveis independentes.")
            return []
        self.store.save_topics(day, top)
        self.channel.send_topics(day, top)
        return top

    def _sensitive(self, topic: Topic) -> bool:
        return bool(blocked_words((topic.title, topic.summary, topic.context), self.blocklist))

    # --- escolha, geração e decisões ---------------------------------------------------------------------------
    def stage_poll(self, now: datetime) -> None:
        for event in self.channel.poll():
            if isinstance(event, TopicsChosen):
                self._on_choice(event, now)
            elif isinstance(event, ProposalDecision):
                self._on_decision(event, now)
            elif isinstance(event, Feedback):
                self._on_feedback(event, now)

    def _on_choice(self, ev: TopicsChosen, now: datetime) -> None:
        if self.store.choice(ev.day):
            return
        known = {t.id for t in self.store.topics(ev.day)}
        ids = list(ev.topic_ids)
        if len(ids) != self.settings.picks_per_day or len(set(ids)) != len(ids) or not set(ids) <= known:
            self.channel.notify(f"Escolha inválida: preciso de {self.settings.picks_per_day} temas diferentes.")
            return
        self.store.save_choice(ev.day, ids)
        for topic_id in ids:
            self._generate(self.store.topic(topic_id), now)

    def _generate(self, topic: Topic, now: datetime) -> None:
        try:
            pair = generate_proposals(topic, self.llm)
        except Exception as e:
            self.channel.notify(f"Não consegui gerar propostas para «{topic.title}»: {e}")
            return
        self.store.save_proposals(pair)
        for p in pair:
            self._produce(p, topic, now)

    def _produce(self, p: Proposal, topic: Topic, now: datetime) -> bool:
        text = run_gates(p, topic, [], True, self.blocklist, caption=caption_for(p, topic))  # texto primeiro: não se gasta voz em propostas vetadas
        if not text.passed:
            return self._reject(p, topic, text.reasons, now)
        assets = []
        try:
            for lang in PUBLISH_LANGUAGES:
                assets += self.builder(p, lang, self.voice, self.visuals, self.llm, self.workdir)[1]
        except Exception as e:
            return self._reject(p, topic, [f"falha na produção do vídeo: {e}"], now)
        legal = copyright_gate(assets)
        if not legal.passed:
            return self._reject(p, topic, legal.reasons, now)
        if not self.store.set_status_if(p.id, ("draft", "revising"), "gated", at=now):
            return False  # recusada (ou já tratada) enquanto se produzia
        self.channel.send_proposal(p, topic)
        return True

    def _reject(self, p: Proposal, topic: Topic, reasons: Sequence[str], now: datetime) -> bool:
        self.store.set_status(p.id, "rejected", reasons, at=now)
        self.channel.notify(f"Proposta {p.variant} de «{topic.title}» rejeitada: {'; '.join(reasons)}")
        return False

    def _status(self, proposal_id: str) -> str | None:
        try:
            return self.store.status(proposal_id)
        except KeyError:
            return None

    def _on_decision(self, ev: ProposalDecision, now: datetime) -> None:
        day = today_lisbon(now)
        status = self._status(ev.proposal_id)
        if ev.action == "accept" and status == "gated":
            self.store.set_status(ev.proposal_id, "approved", at=now)
        elif ev.action == "reject" and status in ("gated", "approved", "revising"):
            self.store.set_status(ev.proposal_id, "rejected", ["recusada pelo Ricardo"], at=now)
        elif ev.action == "improve" and status in ("gated", "approved"):
            self.store.set_status(ev.proposal_id, "revising", at=now)
            self.channel.ask_feedback(ev.proposal_id)
        else:
            return
        self.store.record_decision(ev.proposal_id, ev.action, day)  # conta como intervenção (metrics.success)

    def _on_feedback(self, ev: Feedback, now: datetime) -> None:
        day = today_lisbon(now)
        if self._status(ev.proposal_id) != "revising":
            return
        self.store.record_decision(ev.proposal_id, "feedback", day)
        if self.store.bump_revision(ev.proposal_id) > self.settings.revision_limit:
            self.store.set_status(ev.proposal_id, "rejected", ["limite de revisões atingido"], at=now)
            self.channel.notify("Atingi o limite de revisões desta proposta; ficou rejeitada.")
            return
        p = self.store.proposal(ev.proposal_id)
        topic = self.store.topic(p.topic_id)
        try:
            new = revise_proposal(p, topic, ev.text, self.llm)
        except Exception as e:
            self.store.set_status(p.id, "gated", at=now)
            self.channel.notify(f"Não consegui rever a proposta {p.variant} de «{topic.title}»: {e}")
            return
        self.store.replace_proposal(new)
        self._produce(new, topic, now)  # continua `revising` até as barreiras e o vídeo novo estarem prontos

    # --- publicação ---------------------------------------------------------------------------------------------
    def stage_publish(self, now: datetime) -> dict[str, str]:
        """Aprovadas saem sempre. O período de aceitação obrigatória conta desde a 1.ª publicação; fora dele
        saem também as `gated` cujo tema é de hoje e que estão `gated` há `publish_hold_minutes` (janela de revisão).
        As `gated` de dias anteriores expiram: nada se publica em massa."""
        today = today_lisbon(now)
        first_pub = self.store.first_publication_day()
        needs_accept = first_pub is None or (today - first_pub).days < self.settings.require_accept_days
        eligible = self.store.proposals_by_status("approved")
        if not needs_accept:
            eligible += self._auto_publishable(now, today)
        published: dict[str, str] = {}
        for p in eligible:
            topic = self.store.topic(p.topic_id)
            video = self.workdir / f"{p.id}-{PUBLISH_LANGUAGES[0]}.mp4"
            for platform, publisher in self.publishers.items():
                if self.store.publication(p.id, platform):
                    continue
                if not self.store.claim_publication(p.id, platform, now):
                    continue  # outra execução está a publicá-la agora
                if not self._eligible_now(p.id, now, today, needs_accept):
                    self.store.release_claim(p.id, platform)
                    break  # recusada, em revisão ou mudou entretanto: relê-se o estado antes de cada upload
                p = self.store.proposal(p.id)  # texto atual (pode ter sido revisto)
                caption = caption_for(p, topic)
                try:
                    external_id = publisher.publish(video, caption, True, p.id)
                except Exception as e:
                    self.store.release_claim(p.id, platform)
                    self.channel.notify(f"Falhou a publicação da proposta {p.variant} de «{topic.title}» "
                                        f"em {platform}: {e}")
                    continue
                self.store.record_publication(p.id, platform, external_id, today_lisbon(now))
                published[f"{p.id}:{platform}"] = external_id
                self.channel.notify(self._published_note(platform, p, topic, external_id, caption))
            if self.publishers and all(self.store.publication(p.id, pl) for pl in self.publishers):
                self.store.set_status_if(p.id, ("approved", "gated"), "published", at=now)
        return published

    def _auto_publishable(self, now: datetime, today: date) -> list[Proposal]:
        out = []
        for p in self.store.proposals_by_status("gated"):
            if self.store.topic_day(p.topic_id) < today:
                self.store.set_status_if(p.id, ("gated",), "expired", ["tema de um dia anterior: não se publica"],
                                         at=now)
            elif self._eligible_now(p.id, now, today, needs_accept=False):
                out.append(p)
        return out

    def _eligible_now(self, proposal_id: str, now: datetime, today: date, needs_accept: bool) -> bool:
        status = self._status(proposal_id)
        if status == "approved":
            return True
        if status != "gated" or needs_accept:
            return False
        since = self.store.status_at(proposal_id)
        hold = timedelta(minutes=self.settings.publish_hold_minutes)
        topic_id = self.store.proposal(proposal_id).topic_id
        return self.store.topic_day(topic_id) == today and since is not None and now - since >= hold

    @staticmethod
    def _published_note(platform: str, p: Proposal, topic: Topic, external_id: str, caption: str) -> str:
        if platform == "tiktok":
            return (f"Rascunho no TikTok ({external_id}): abre a app, cola a legenda e liga o rótulo de IA.\n{caption}")
        return f"Publicado em {platform}: proposta {p.variant} de «{topic.title}» ({external_id})."
