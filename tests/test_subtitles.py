import pytest
from builders import make_topic
from fakes import FakeLLM
from onlinebusinesses.subtitles import Segment, build_srt, languages_for, localize, split_script


def test_build_srt_format():
    srt = build_srt([Segment(0.0, 2.5, "texto"), Segment(2.5, 3661.007, "outro")])
    assert srt == "1\n00:00:00,000 --> 00:00:02,500\ntexto\n\n2\n00:00:02,500 --> 01:01:01,007\noutro\n\n"


def test_split_script_has_no_overlaps_and_matches_reading_speed():
    words = "um dois três quatro cinco seis sete oito nove dez".split()
    segs = split_script(" ".join(words), wpm=170, max_words=8)
    assert [len(s.text.split()) for s in segs] == [8, 2]
    assert segs[0].start == 0.0 and all(a.end <= b.start for a, b in zip(segs, segs[1:]))
    assert segs[-1].end == pytest.approx(len(words) / 170 * 60)


def test_split_script_empty_is_empty():
    assert split_script("   ") == []


def test_languages_for_depends_on_travels():
    assert languages_for(make_topic(travels=False)) == ["pt-PT"]
    assert languages_for(make_topic(travels=True)) == ["pt-PT", "pt-BR", "es"]


def test_localize_asks_for_adaptation_not_literal_translation():
    llm = FakeLLM(["  Texto adaptado.  "])
    out = localize("Piada sobre o IRS.", "pt-BR", llm)
    system, user = llm.calls[0]
    assert out == "Texto adaptado."
    assert "pt-BR" in system + user and "Piada sobre o IRS." in user
    assert "Adapta" in system and "não traduzas" in system


def test_localize_rejects_empty_answer():
    with pytest.raises(ValueError):
        localize("x", "es", FakeLLM(["   "]))
