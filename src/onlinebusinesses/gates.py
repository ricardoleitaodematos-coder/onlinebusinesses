from __future__ import annotations

import re
import tomllib
import unicodedata
from pathlib import Path
from typing import Mapping, Sequence

from .models import Asset, GateResult, Proposal, Topic

_REALISTIC = {"fotorrealista", "fotorrealismo", "photorealistic", "photorealism", "deepfake", "hiperrealista"}
MAX_TRUSTED_TIER = 2


def _words(text: str) -> set[str]:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return set(re.findall(r"[a-z0-9]+", plain))


def _result(reasons: Sequence[str]) -> GateResult:
    return GateResult(passed=not reasons, reasons=tuple(reasons))


def load_blocklist(path: Path) -> dict[str, list[str]]:
    return {lang: list(words) for lang, words in tomllib.loads(Path(path).read_text(encoding="utf-8")).items()}


def fact_gate(p: Proposal, topic: Topic) -> GateResult:
    reasons: list[str] = []
    tiers = {s.id: s.tier for s in topic.sources}
    if len({s.domain for s in topic.sources if s.tier <= MAX_TRUSTED_TIER}) < 2:
        reasons.append("tema com menos de 2 fontes independentes de nível 1 ou 2")
    if not p.claims:
        reasons.append("proposta sem afirmações com fonte")
    for claim in p.claims:
        unknown = [i for i in claim.source_ids if i not in tiers]
        if unknown or not claim.source_ids:
            reasons.append(f"afirmação cita fonte inexistente: {', '.join(unknown) or '(nenhuma)'}")
        elif not any(tiers[i] <= MAX_TRUSTED_TIER for i in claim.source_ids):
            reasons.append(f"afirmação só cita fontes de nível 3: {claim.text}")
    return _result(reasons)


def blocked_words(texts: Sequence[str], blocklist: Mapping[str, Sequence[str]]) -> list[str]:
    """Palavras vetadas presentes em qualquer dos textos (palavra inteira, sem maiúsculas nem acentos)."""
    blocked = {w for terms in blocklist.values() for w in map(_words_one, terms)} - {""}
    return sorted(_words(" ".join(texts)) & blocked)


def sensitivity_gate(p: Proposal, blocklist: Mapping[str, Sequence[str]],
                     extra_texts: Sequence[str] = ()) -> GateResult:
    """Guião, prompts visuais e textos extra (legenda final, título e resumo do tema)."""
    reasons = [f"palavra vetada: {w}" for w in blocked_words((p.script_pt, *p.visual_prompts, *extra_texts),
                                                              blocklist)]
    prompt_words = _words(" ".join(p.visual_prompts))
    reasons += [f"visual realista não permitido: {w}" for w in sorted(prompt_words & _REALISTIC)]
    return _result(reasons)


def _words_one(term: str) -> str:
    found = _words(term)
    return next(iter(found)) if len(found) == 1 else ""


def copyright_gate(assets: Sequence[Asset]) -> GateResult:
    reasons = []
    for a in assets:
        if a.origin == "third-party":
            reasons.append(f"material de terceiros: {a.path}")
        elif a.origin == "licensed-free" and not a.license:
            reasons.append(f"material livre sem licença indicada: {a.path}")
    return _result(reasons)


def label_gate(p: Proposal, ai_label_set: bool) -> GateResult:
    if (p.synthetic_voice or p.synthetic_visuals) and not ai_label_set:
        return _result(["falta o rótulo de IA da plataforma"])
    return _result([])


def run_gates(p: Proposal, topic: Topic, assets: Sequence[Asset], ai_label_set: bool,
              blocklist: Mapping[str, Sequence[str]], caption: str = "") -> GateResult:
    sensitive = sensitivity_gate(p, blocklist, (topic.title, topic.summary, caption))
    reasons = (*fact_gate(p, topic).reasons, *sensitive.reasons,
               *copyright_gate(assets).reasons, *label_gate(p, ai_label_set).reasons)
    return _result(reasons)
