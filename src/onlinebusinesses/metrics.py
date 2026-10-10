from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Mapping

from .publishers.base import Publisher
from .store import Store

WINDOW_DAYS = 7


def collect_insights(store: Store, publishers: Mapping[str, Publisher]) -> int:
    """Vai buscar as métricas de tudo o que foi publicado; saltar o que a plataforma ainda não dá (TikTok rascunho)."""
    collected = 0
    for proposal_id, platform, external_id in store.all_publications():
        publisher = publishers.get(platform)
        if publisher is None:
            continue
        try:
            insights = publisher.insights(external_id)
        except Exception:  # NotImplementedError e falhas de rede: não pára o relatório
            continue
        store.save_insights(proposal_id, platform, insights)
        collected += 1
    return collected


def _per_day(store: Store, start: date) -> dict[date, int]:
    counts: dict[date, int] = {start + timedelta(days=i): 0 for i in range(WINDOW_DAYS)}
    for *_, day in store.publications_between(start, start + timedelta(days=WINDOW_DAYS - 1)):
        counts[day] += 1
    return counts


def success(store: Store, start: date) -> bool:
    """Critério da fase 0: publicação em 7 dias seguidos, sem decisões do Ricardo nesse período."""
    end = start + timedelta(days=WINDOW_DAYS - 1)
    return all(n > 0 for n in _per_day(store, start).values()) and store.decisions_between(start, end) == 0


def weekly_report(store: Store, start: date) -> str:
    end = start + timedelta(days=WINDOW_DAYS - 1)
    lines = [f"Semana de {start} a {end}", "Publicações por dia:"]
    lines += [f"  {day}: {n}" for day, n in _per_day(store, start).items()]
    lines.append(f"Sucesso: {'sim' if success(store, start) else 'não'}")
    totals: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for proposal_id, *_ in store.publications_between(start, end):
        try:
            proposal = store.proposal(proposal_id)
        except KeyError:
            continue
        totals[proposal.topic_id][proposal.variant] += [ins for _, ins in store.insights_for(proposal_id)]
    for topic_id, variants in totals.items():
        lines.append(f"Tema «{store.topic(topic_id).title}»")
        for variant in sorted(variants):
            rows = variants[variant]
            watch = sum(r.avg_watch_s for r in rows) / len(rows) if rows else 0.0
            lines.append(f"  {variant}: visualizações {sum(r.views for r in rows)}, gostos {sum(r.likes for r in rows)}, "
                         f"comentários {sum(r.comments for r in rows)}, partilhas {sum(r.shares for r in rows)}, "
                         f"tempo médio {watch:.1f}s")
    return "\n".join(lines)
