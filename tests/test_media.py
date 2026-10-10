import json
import shutil
import subprocess
from pathlib import Path

import pytest
from builders import make_proposal
from fakes import FakeLLM
from onlinebusinesses.media import assemble, audio_duration, build_video
from onlinebusinesses.subtitles import Segment, build_srt

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg não instalado")


def ff(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


@pytest.fixture
def media(tmp_path):
    audio = tmp_path / "a.wav"
    ff("-f", "lavfi", "-i", "sine=frequency=440:duration=3", str(audio))
    frames = []
    for i, color in enumerate(("red", "green", "blue")):
        f = tmp_path / f"f{i}.png"
        ff("-f", "lavfi", "-i", f"color=c={color}:s=640x360", "-frames:v", "1", str(f))
        frames.append(f)
    srt = tmp_path / "s.srt"
    srt.write_text(build_srt([Segment(0, 3, "legenda")]), encoding="utf-8")
    return audio, frames, srt


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
                          "-of", "json", str(path)], check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def test_audio_duration(media):
    assert audio_duration(media[0]) == pytest.approx(3.0, abs=0.1)


def test_assemble_is_vertical_and_as_long_as_the_audio(media, tmp_path):
    audio, frames, srt = media
    out = assemble(audio, frames, srt, tmp_path / "out.mp4")
    info = probe(out)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (video["width"], video["height"]) == (1080, 1920)
    assert any(s["codec_type"] == "audio" for s in info["streams"])
    assert float(info["format"]["duration"]) == pytest.approx(3.0, abs=0.5)


class FakeVoice:
    def __init__(self, wav):
        self.wav, self.calls = wav, []

    def synthesize(self, text, lang, out):
        self.calls.append((text, lang))
        shutil.copy(self.wav, out)
        return out


class FakeVisuals:
    def __init__(self, pngs):
        self.pngs = pngs

    def render(self, prompts, style, out_dir):
        out_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for i, _ in enumerate(prompts):
            dest = out_dir / f"{i}.png"
            shutil.copy(self.pngs[i % len(self.pngs)], dest)
            paths.append(dest)
        return paths


def test_build_video_marks_every_asset_generated_and_skips_localize_for_pt_pt(media, tmp_path):
    audio, frames, _ = media
    llm = FakeLLM(["não deve ser chamado"])
    voice = FakeVoice(audio)
    out, assets = build_video(make_proposal(), "pt-PT", voice, FakeVisuals(frames), llm, tmp_path / "w")
    assert out.exists() and out.suffix == ".mp4"
    assert llm.calls == [] and voice.calls[0][1] == "pt-PT"
    assert assets and all(a.origin == "generated" for a in assets)


def test_build_video_localizes_for_other_languages(media, tmp_path):
    audio, frames, _ = media
    llm = FakeLLM(["Texto adaptado para o Brasil."])
    voice = FakeVoice(audio)
    out, _ = build_video(make_proposal(), "pt-BR", voice, FakeVisuals(frames), llm, tmp_path / "w")
    assert voice.calls == [("Texto adaptado para o Brasil.", "pt-BR")]
    assert "Texto adaptado" in (tmp_path / "w" / f"{make_proposal().id}-pt-BR.srt").read_text(encoding="utf-8")


def test_build_video_uses_the_given_script_and_does_not_localize_again(media, tmp_path):
    audio, frames, _ = media
    llm = FakeLLM(["não deve ser chamado"])
    voice = FakeVoice(audio)
    build_video(make_proposal(), "es", voice, FakeVisuals(frames), llm, tmp_path / "w", script="Texto ya adaptado.")
    assert llm.calls == [] and voice.calls == [("Texto ya adaptado.", "es")]
    assert "Texto ya adaptado." in (tmp_path / "w" / f"{make_proposal().id}-es.srt").read_text(encoding="utf-8")
