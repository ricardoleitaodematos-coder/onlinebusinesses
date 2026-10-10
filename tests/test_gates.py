from pathlib import Path

import pytest
from builders import make_proposal, make_source, make_topic
from onlinebusinesses.gates import (copyright_gate, fact_gate, label_gate, load_blocklist, run_gates,
                                    sensitivity_gate)
from onlinebusinesses.models import Asset, Claim

TOPIC = make_topic("t1")
SID = TOPIC.sources[0].id
BLOCK = {"pt": ["morreu"], "es": ["muertos"], "en": ["minor"]}
CLEAN = [Asset("v.mp4", "generated", None)]


def test_fact_gate_passes_with_cited_source():
    assert fact_gate(make_proposal(topic=TOPIC), TOPIC).passed


def test_fact_gate_fails_without_claims():
    assert not fact_gate(make_proposal(topic=TOPIC, claims=()), TOPIC).passed


def test_fact_gate_fails_on_unknown_source_id():
    p = make_proposal(topic=TOPIC, claims=(Claim("x", ("inventado",)),))
    assert "inventado" in " ".join(fact_gate(p, TOPIC).reasons)


def test_fact_gate_fails_when_topic_has_one_trusted_domain():
    t = make_topic("t1", [make_source("a.pt", 1, sid="1"), make_source("a.pt", 1, sid="2")])
    assert not fact_gate(make_proposal(topic=t, claims=(Claim("x", ("1",)),)), t).passed


def test_fact_gate_fails_when_claim_cites_only_tier3():
    t = make_topic("t1", [make_source("a.pt", 1, sid="1"), make_source("b.com", 2, sid="2"),
                          make_source("blog.example", 3, sid="3")])
    assert not fact_gate(make_proposal(topic=t, claims=(Claim("x", ("3",)),)), t).passed


@pytest.mark.parametrize("word", ["morreu", "MORREU", "muertos", "minor"])
def test_sensitivity_blocks_words_in_any_language(word):
    p = make_proposal(script=f"O ministro {word} ontem.")
    assert not sensitivity_gate(p, BLOCK).passed


def test_sensitivity_ignores_accents_and_whole_word_only():
    assert sensitivity_gate(make_proposal(script="O morreúdo não conta; minority também não."), BLOCK).passed
    assert not sensitivity_gate(make_proposal(script="Ele MORREÚ."), {"pt": ["morreu"]}).passed


def test_sensitivity_blocks_blocked_word_in_visual_prompts():
    p = make_proposal(prompts=("cartoon de um muertos",))
    assert not sensitivity_gate(p, BLOCK).passed


def test_sensitivity_blocks_photorealistic_prompts():
    p = make_proposal(prompts=("retrato fotorrealista do ministro",))
    assert not sensitivity_gate(p, BLOCK).passed
    assert not sensitivity_gate(make_proposal(prompts=("a deepfake of the PM",)), BLOCK).passed


def test_copyright_blocks_third_party_and_unlicensed():
    assert copyright_gate(CLEAN).passed
    assert not copyright_gate([Asset("x.mp3", "third-party", None)]).passed
    assert not copyright_gate([Asset("m.mp3", "licensed-free", None)]).passed
    assert copyright_gate([Asset("m.mp3", "licensed-free", "CC0")]).passed


def test_label_gate_requires_label_for_synthetic_media():
    p = make_proposal(voice=True, visuals=False)
    assert not label_gate(p, False).passed
    assert label_gate(p, True).passed
    assert label_gate(make_proposal(voice=False, visuals=False), False).passed


def test_run_gates_clean_case_passes():
    assert run_gates(make_proposal(topic=TOPIC), TOPIC, CLEAN, True, BLOCK) .passed


def test_run_gates_collects_every_reason():
    p = make_proposal(topic=TOPIC, script="Ele morreu.")
    r = run_gates(p, TOPIC, [Asset("x", "third-party", None)], False, BLOCK)
    assert not r.passed and len(r.reasons) == 3


def test_load_blocklist_reads_languages(tmp_path):
    f = tmp_path / "b.toml"
    f.write_text('pt = ["a"]\nes = ["b"]\n', encoding="utf-8")
    assert load_blocklist(f) == {"pt": ["a"], "es": ["b"]}


def test_shipped_blocklist_covers_three_languages():
    bl = load_blocklist(Path(__file__).parent.parent / "config" / "blocklist.toml")
    assert set(bl) == {"pt", "es", "en"}
    assert not sensitivity_gate(make_proposal(script="Houve um atentado."), bl).passed
    assert sensitivity_gate(make_proposal(script="O governo aprovou um orçamento."), bl).passed


def test_run_gates_checks_caption_and_topic_title():
    p = make_proposal(topic=TOPIC)
    assert not run_gates(p, TOPIC, CLEAN, True, BLOCK, caption="Ele morreu.\n\nFontes: a.pt").passed
    sad = make_topic("t1", TOPIC.sources)
    sad = type(sad)(**{**sad.__dict__, "title": "Ministro morreu", "summary": "resumo"})
    assert "palavra vetada: morreu" in run_gates(p, sad, CLEAN, True, BLOCK).reasons
