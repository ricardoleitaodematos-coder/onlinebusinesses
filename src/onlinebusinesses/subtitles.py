from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

from .llm import LLMClient
from .models import Topic


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str


def _stamp(seconds: float) -> str:
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def build_srt(segments: Sequence[Segment]) -> str:
    return "".join(f"{i}\n{_stamp(s.start)} --> {_stamp(s.end)}\n{s.text}\n\n" for i, s in enumerate(segments, 1))


def split_script(script: str, wpm: int = 170, max_words: int = 8) -> list[Segment]:
    words = script.split()
    per_word = 60 / wpm
    return [Segment(start=i * per_word, end=min(i + max_words, len(words)) * per_word,
                    text=" ".join(words[i:i + max_words])) for i in range(0, len(words), max_words)]


def languages_for(topic: Topic) -> list[str]:
    return ["pt-PT", "pt-BR", "es"] if topic.travels else ["pt-PT"]


def localize(script_pt: str, lang: Literal["pt-BR", "es"], llm: LLMClient) -> str:
    system = (f"Adapta este guião de comédia satírica de PT-PT para {lang}: não traduzas à letra "
              "expressões, moeda, instituições nem referências locais, e mantém o tom, o ritmo e os factos. "
              "Responde só com o guião adaptado.")
    out = llm.complete(system, f"Língua de destino: {lang}\n\n{script_pt}").strip()
    if not out:
        raise ValueError("adaptação vazia")
    return out
