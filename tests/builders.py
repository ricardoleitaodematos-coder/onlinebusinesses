from datetime import datetime, timezone

from onlinebusinesses.models import Claim, Proposal, Source, Topic

NOW = datetime(2026, 10, 10, 8, 0, tzinfo=timezone.utc)


def make_source(domain="a.pt", tier=1, title="Governo anuncia medida", sid=None, published_at=NOW):
    return Source(
        id=sid or f"s-{domain}",
        url=f"https://{domain}/n/1",
        domain=domain,
        title=title,
        outlet=domain,
        published_at=published_at,
        tier=tier,
    )


def make_topic(tid="t1", sources=None, category="ai", travels=True, context=""):
    sources = tuple(sources) if sources is not None else (make_source("a.pt"), make_source("b.com"))
    return Topic(id=tid, title="Governo anuncia medida", summary="resumo", sources=sources,
                 category=category, travels=travels, context=context)


def make_proposal(pid="ab12cd34", topic=None, variant="A", claims=None, script="Texto da piada.",
                  prompts=("cartoon de um robô",), style="cartoon", voice=True, visuals=True):
    topic = topic or make_topic()
    claims = claims if claims is not None else (Claim(text="facto", source_ids=(topic.sources[0].id,)),)
    return Proposal(id=pid, topic_id=topic.id, variant=variant, script_pt=script, claims=tuple(claims),
                    visual_prompts=tuple(prompts), visual_style=style,
                    synthetic_voice=voice, synthetic_visuals=visuals)
