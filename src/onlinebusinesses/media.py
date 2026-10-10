from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Protocol, Sequence

from .llm import LLMClient
from .models import Asset, Proposal
from .subtitles import Segment, build_srt, localize, split_script


class Voice(Protocol):
    def synthesize(self, text: str, lang: str, out: Path) -> Path: ...


class Visuals(Protocol):
    def render(self, prompts: Sequence[str], style: str, out_dir: Path) -> list[Path]: ...


def audio_duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         check=True, capture_output=True, text=True).stdout
    return float(out.strip())


def assemble(audio: Path, frames: Sequence[Path], srt: Path, out: Path) -> Path:
    if not frames:
        raise ValueError("sem imagens para montar o vídeo")
    audio, srt, out = Path(audio).resolve(), Path(srt).resolve(), Path(out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    n, per = len(frames), audio_duration(audio) / len(frames)
    cmd = ["ffmpeg", "-v", "error", "-y"]
    for f in frames:
        cmd += ["-loop", "1", "-t", f"{per:.3f}", "-i", str(Path(f).resolve())]
    cmd += ["-i", str(audio)]
    scale = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30"
    graph = [f"[{i}:v]{scale}[v{i}]" for i in range(n)]
    graph.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[v]")
    graph.append(f"[v]subtitles={srt.name}:force_style='Alignment=2,FontSize=14'[vs]")
    cmd += ["-filter_complex", ";".join(graph), "-map", "[vs]", "-map", f"{n}:a", "-c:v", "libx264",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out)]
    subprocess.run(cmd, check=True, capture_output=True, cwd=srt.parent)
    return out


def _fit(segments: Sequence[Segment], duration: float) -> list[Segment]:
    if not segments:
        return []
    k = duration / segments[-1].end
    return [Segment(s.start * k, s.end * k, s.text) for s in segments]


def build_video(p: Proposal, lang: str, voice: Voice, visuals: Visuals, llm: LLMClient,
                workdir: Path) -> tuple[Path, list[Asset]]:
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    text = p.script_pt if lang == "pt-PT" else localize(p.script_pt, lang, llm)  # type: ignore[arg-type]
    audio = voice.synthesize(text, lang, workdir / f"{p.id}-{lang}.wav")
    frames = visuals.render(p.visual_prompts, p.visual_style, workdir / f"{p.id}-frames")
    srt = workdir / f"{p.id}-{lang}.srt"
    srt.write_text(build_srt(_fit(split_script(text), audio_duration(audio))), encoding="utf-8")
    video = assemble(audio, frames, srt, workdir / f"{p.id}-{lang}.mp4")
    assets = [Asset(str(audio), "generated", None), *(Asset(str(f), "generated", None) for f in frames),
              Asset(str(video), "generated", None)]
    return video, assets
