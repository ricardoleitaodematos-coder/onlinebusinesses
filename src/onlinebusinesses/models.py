from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Literal, Self

Tier = Literal[1, 2, 3]
Category = Literal["ai", "geopolitics", "national", "other"]
Variant = Literal["A", "B"]
VisualStyle = Literal["cartoon", "illustration", "abstract"]
Origin = Literal["generated", "licensed-free", "third-party"]


def _plain(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (tuple, list)):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    return value


class _Json:
    def to_json(self) -> str:
        return json.dumps(_plain(asdict(self)), ensure_ascii=False)  # type: ignore[arg-type]

    @classmethod
    def from_json(cls, s: str) -> Self:
        return cls.from_dict(json.loads(s))

    @classmethod
    def from_dict(cls, d: dict) -> Self:
        return cls(**d)


@dataclass(frozen=True)
class Source(_Json):
    id: str
    url: str
    domain: str
    title: str
    outlet: str
    published_at: datetime
    tier: Tier

    @classmethod
    def from_dict(cls, d: dict) -> Self:
        return cls(**{**d, "published_at": datetime.fromisoformat(d["published_at"])})


@dataclass(frozen=True)
class Topic(_Json):
    id: str
    title: str
    summary: str
    sources: tuple[Source, ...]
    category: Category
    travels: bool
    context: str

    @classmethod
    def from_dict(cls, d: dict) -> Self:
        return cls(**{**d, "sources": tuple(Source.from_dict(s) for s in d["sources"])})


@dataclass(frozen=True)
class Claim(_Json):
    text: str
    source_ids: tuple[str, ...]

    @classmethod
    def from_dict(cls, d: dict) -> Self:
        return cls(text=d["text"], source_ids=tuple(d["source_ids"]))


@dataclass(frozen=True)
class Proposal(_Json):
    id: str
    topic_id: str
    variant: Variant
    script_pt: str
    claims: tuple[Claim, ...]
    visual_prompts: tuple[str, ...]
    visual_style: VisualStyle
    synthetic_voice: bool
    synthetic_visuals: bool

    @classmethod
    def from_dict(cls, d: dict) -> Self:
        return cls(**{**d, "claims": tuple(Claim.from_dict(c) for c in d["claims"]),
                      "visual_prompts": tuple(d["visual_prompts"])})


@dataclass(frozen=True)
class Asset(_Json):
    path: str
    origin: Origin
    license: str | None


@dataclass(frozen=True)
class GateResult(_Json):
    passed: bool
    reasons: tuple[str, ...]

    @classmethod
    def from_dict(cls, d: dict) -> Self:
        return cls(passed=d["passed"], reasons=tuple(d["reasons"]))


@dataclass(frozen=True)
class Insights(_Json):
    views: int
    likes: int
    comments: int
    shares: int
    avg_watch_s: float
