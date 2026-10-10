from __future__ import annotations

import hashlib

from .llm import LLMClient, parse_json_object
from .models import Claim, Proposal, Topic

STYLES = ("cartoon", "illustration", "abstract")

SYSTEM = (
    "És argumentista de comédia satírica sobre a atualidade, em PT-PT, tom jovem e atual, com sátira e preocupação. "
    "Parte de factos verdadeiros e exagera só a piada. Cada afirmação factual tem de citar os ids das fontes dadas. "
    "Nunca uses mortes ou tragédias recentes, menores, pessoas privadas, nem guerra como piada. "
    "Visuais só em estilo cartoon, illustration ou abstract: nunca fotorrealista nem pessoas reais. "
    "Responde apenas com JSON."
)
_FORMAT = ('{"proposals": [{"variant": "A", "script_pt": "...", "claims": [{"text": "...", "source_ids": ["id"]}], '
           '"visual_prompts": ["..."], "visual_style": "cartoon"}, {"variant": "B", ...}]}')


class ProposalError(Exception):
    pass


def _topic_brief(topic: Topic) -> str:
    sources = "\n".join(f"- id={s.id} {s.outlet}: {s.title} ({s.url})" for s in topic.sources)
    return f"Tema: {topic.title}\n{topic.summary}\nFontes:\n{sources}\nContexto:\n{topic.context}"


def _valid_body(d: object, topic: Topic) -> dict:
    ids = {s.id for s in topic.sources}
    if not isinstance(d, dict) or not str(d.get("script_pt", "")).strip():
        raise ProposalError("guião em falta")
    claims = d.get("claims")
    if not isinstance(claims, list) or not claims:
        raise ProposalError("sem afirmações")
    for c in claims:
        cited = c.get("source_ids") if isinstance(c, dict) else None
        if not str(c.get("text", "") if isinstance(c, dict) else "").strip() or not cited or not set(cited) <= ids:
            raise ProposalError("afirmação sem fonte válida")
    prompts = d.get("visual_prompts")
    if not isinstance(prompts, list) or not prompts or not all(isinstance(p, str) for p in prompts):
        raise ProposalError("visual_prompts inválidos")
    if d.get("visual_style") not in STYLES:
        raise ProposalError("estilo visual não permitido")
    return d


def _build(topic: Topic, pid: str, variant: str, d: dict) -> Proposal:
    return Proposal(id=pid, topic_id=topic.id, variant=variant, script_pt=d["script_pt"].strip(),  # type: ignore[arg-type]
                    claims=tuple(Claim(c["text"], tuple(c["source_ids"])) for c in d["claims"]),
                    visual_prompts=tuple(d["visual_prompts"]), visual_style=d["visual_style"],
                    synthetic_voice=True, synthetic_visuals=True)


def _ask(llm: LLMClient, user: str, parse):
    last: Exception | None = None
    for _ in range(2):
        try:
            return parse(parse_json_object(llm.complete(SYSTEM, user)))
        except ProposalError as e:
            last = e
    raise ProposalError(str(last))


def generate_proposals(topic: Topic, llm: LLMClient) -> tuple[Proposal, Proposal]:
    def parse(data: dict | None) -> tuple[Proposal, Proposal]:
        items = (data or {}).get("proposals")
        if not isinstance(items, list) or len(items) != 2:
            raise ProposalError("esperadas duas propostas")
        out = []
        for variant, item in zip("AB", items):
            body = _valid_body(item, topic)
            pid = hashlib.sha1(f"{topic.id}:{variant}".encode()).hexdigest()[:8]
            out.append(_build(topic, pid, variant, body))
        return out[0], out[1]

    return _ask(llm, f"{_topic_brief(topic)}\n\nDuas propostas diferentes (A e B), formato:\n{_FORMAT}", parse)


def revise_proposal(p: Proposal, topic: Topic, feedback: str, llm: LLMClient) -> Proposal:
    def parse(data: dict | None) -> Proposal:
        return _build(topic, p.id, p.variant, _valid_body(data, topic))

    user = (f"{_topic_brief(topic)}\n\nProposta atual ({p.variant}):\n{p.script_pt}\n\n"
            f"Pedido de melhoria do Ricardo: {feedback}\n\nDevolve só a proposta revista como um objeto JSON "
            '{"script_pt": "...", "claims": [...], "visual_prompts": [...], "visual_style": "cartoon"}.')
    return _ask(llm, user, parse)
