from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Callable, Mapping, Sequence

from .brief import Channel, Feedback, ProposalDecision, TopicsChosen
from .config import Settings, load_feeds, today_lisbon
from .gates import copyright_gate, run_gates
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


def caption_for(p: Proposal, topic: Topic) -> str:
    domains = ", ".join(sorted({s.domain for s in topic.sources if s.tier <= 2}))
    return f"{topic.title}\n\nConteúdo satírico gerado com IA. Fontes: {domains}"


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
        topics = [corroborate(t, self.search, self.tiers, now, aliases=self.aliases) for t in cluster_topics(items)]
        top = rank_topics(topics, self.settings.topics_per_day)
        top = classify_topics([add_context(t, self.http) for t in top], self.llm)
        if not top:
            self.channel.notify("Hoje não encontrei temas com duas fontes fiáveis independentes.")
            return []
        self.store.save_topics(day, top)
        self.channel.send_topics(day, top)
        return top

    # --- escolha, geração e decisões ---------------------------------------------------------------------------
    def stage_poll(self, now: datetime) -> None:
        for event in self.channel.poll():
            if isinstance(event, TopicsChosen):
                self._on_choice(event)
            elif isinstance(event, ProposalDecision):
                self._on_decision(event, today_lisbon(now))
            elif isinstance(event, Feedback):
                self._on_feedback(event, today_lisbon(now))

    def _on_choice(self, ev: TopicsChosen) -> None:
        if self.store.choice(ev.day):
            return
        known = {t.id for t in self.store.topics(ev.day)}
        ids = list(ev.topic_ids)
        if len(ids) != self.settings.picks_per_day or len(set(ids)) != len(ids) or not set(ids) <= known:
            self.channel.notify(f"Escolha inválida: preciso de {self.settings.picks_per_day} temas diferentes.")
            return
        self.store.save_choice(ev.day, ids)
        for topic_id in ids:
            self._generate(self.store.topic(topic_id))

    def _generate(self, topic: Topic) -> None:
        try:
            pair = generate_proposals(topic, self.llm)
        except Exception as e:
            self.channel.notify(f"Não consegui gerar propostas para «{topic.title}»: {e}")
            return
        self.store.save_proposals(pair)
        for p in pair:
            self._produce(p, topic)

    def _produce(self, p: Proposal, topic: Topic) -> bool:
        text = run_gates(p, topic, [], True, self.blocklist)  # texto primeiro: não se gasta voz em propostas vetadas
        if not text.passed:
            return self._reject(p, topic, text.reasons)
        assets = []
        try:
            for lang in PUBLISH_LANGUAGES:
                assets += self.builder(p, lang, self.voice, self.visuals, self.llm, self.workdir)[1]
        except Exception as e:
            return self._reject(p, topic, [f"falha na produção do vídeo: {e}"])
        legal = copyright_gate(assets)
        if not legal.passed:
            return self._reject(p, topic, legal.reasons)
        self.store.set_status(p.id, "gated")
        self.channel.send_proposal(p, topic)
        return True

    def _reject(self, p: Proposal, topic: Topic, reasons: Sequence[str]) -> bool:
        self.store.set_status(p.id, "rejected", reasons)
        self.channel.notify(f"Proposta {p.variant} de «{topic.title}» rejeitada: {'; '.join(reasons)}")
        return False

    def _status(self, proposal_id: str) -> str | None:
        try:
            return self.store.status(proposal_id)
        except KeyError:
            return None

    def _on_decision(self, ev: ProposalDecision, day: date) -> None:
        status = self._status(ev.proposal_id)
        if ev.action == "accept" and status == "gated":
            self.store.set_status(ev.proposal_id, "approved")
        elif ev.action == "reject" and status in ("gated", "approved", "revising"):
            self.store.set_status(ev.proposal_id, "rejected", ["recusada pelo Ricardo"])
        elif ev.action == "improve" and status in ("gated", "approved"):
            self.store.set_status(ev.proposal_id, "revising")
            self.channel.ask_feedback(ev.proposal_id)
        else:
            return
        self.store.record_decision(ev.proposal_id, ev.action, day)  # conta como intervenção (metrics.success)

    def _on_feedback(self, ev: Feedback, day: date) -> None:
        if self._status(ev.proposal_id) != "revising":
            return
        self.store.record_decision(ev.proposal_id, "feedback", day)
        if self.store.bump_revision(ev.proposal_id) > self.settings.revision_limit:
            self.store.set_status(ev.proposal_id, "rejected", ["limite de revisões atingido"])
            self.channel.notify("Atingi o limite de revisões desta proposta; ficou rejeitada.")
            return
        p = self.store.proposal(ev.proposal_id)
        topic = self.store.topic(p.topic_id)
        try:
            new = revise_proposal(p, topic, ev.text, self.llm)
        except Exception as e:
            self.store.set_status(p.id, "gated")
            self.channel.notify(f"Não consegui rever a proposta {p.variant} de «{topic.title}»: {e}")
            return
        self.store.replace_proposal(new)
        self.store.set_status(p.id, "gated")
        self._produce(new, topic)

    # --- publicação ---------------------------------------------------------------------------------------------
    def stage_publish(self, now: datetime) -> dict[str, str]:
        first = self.store.first_day()
        needs_accept = first is None or (today_lisbon(now) - first).days < self.settings.require_accept_days
        eligible = self.store.proposals_by_status("approved")
        if not needs_accept:
            eligible += self.store.proposals_by_status("gated")
        published: dict[str, str] = {}
        for p in eligible:
            topic = self.store.topic(p.topic_id)
            caption = caption_for(p, topic)
            video = self.workdir / f"{p.id}-{PUBLISH_LANGUAGES[0]}.mp4"
            for platform, publisher in self.publishers.items():
                if self.store.publication(p.id, platform):
                    continue
                try:
                    external_id = publisher.publish(video, caption, True, p.id)
                except Exception as e:
                    self.channel.notify(f"Falhou a publicação da proposta {p.variant} de «{topic.title}» "
                                        f"em {platform}: {e}")
                    continue
                self.store.record_publication(p.id, platform, external_id, today_lisbon(now))
                published[f"{p.id}:{platform}"] = external_id
                self.channel.notify(self._published_note(platform, p, topic, external_id, caption))
            if self.publishers and all(self.store.publication(p.id, pl) for pl in self.publishers):
                self.store.set_status(p.id, "published")
        return published

    @staticmethod
    def _published_note(platform: str, p: Proposal, topic: Topic, external_id: str, caption: str) -> str:
        if platform == "tiktok":
            return (f"Rascunho no TikTok ({external_id}): abre a app, cola a legenda e liga o rótulo de IA.\n{caption}")
        return f"Publicado em {platform}: proposta {p.variant} de «{topic.title}» ({external_id})."
