import json
from types import SimpleNamespace

import pytest
from builders import make_proposal, make_topic
from fakes import FakeLLM
from onlinebusinesses.llm import AnthropicClient, build_llm
from onlinebusinesses.proposals import ProposalError, generate_proposals, revise_proposal

TOPIC = make_topic("t1")
SID = TOPIC.sources[0].id


def variant(v, source_ids=(SID,), style="cartoon"):
    return {"variant": v, "script_pt": f"Piada {v}", "claims": [{"text": "facto", "source_ids": list(source_ids)}],
            "visual_prompts": ["cartoon de um robô"], "visual_style": style}


def valid():
    return json.dumps({"proposals": [variant("A"), variant("B")]})


def test_two_variants():
    a, b = generate_proposals(TOPIC, FakeLLM([valid()]))
    assert (a.variant, b.variant) == ("A", "B")
    assert a.topic_id == b.topic_id == "t1" and a.id != b.id and len(a.id) == 8
    assert a.synthetic_voice and a.synthetic_visuals and a.claims[0].source_ids == (SID,)


def test_ids_are_deterministic():
    assert generate_proposals(TOPIC, FakeLLM([valid()]))[0].id == generate_proposals(TOPIC, FakeLLM([valid()]))[0].id


def test_invalid_json_retries_once_then_raises():
    llm = FakeLLM(["isto não é json"])
    with pytest.raises(ProposalError):
        generate_proposals(TOPIC, llm)
    assert len(llm.calls) == 2


def test_retry_recovers_on_second_answer():
    llm = FakeLLM(["lixo", valid()])
    assert len(generate_proposals(TOPIC, llm)) == 2 and len(llm.calls) == 2


def test_unknown_source_id_is_rejected():
    bad = json.dumps({"proposals": [variant("A", ("inventado",)), variant("B")]})
    llm = FakeLLM([bad])
    with pytest.raises(ProposalError):
        generate_proposals(TOPIC, llm)
    assert len(llm.calls) == 2


def test_photorealistic_style_is_rejected():
    bad = json.dumps({"proposals": [variant("A", style="photorealistic"), variant("B")]})
    with pytest.raises(ProposalError):
        generate_proposals(TOPIC, FakeLLM([bad]))


def test_prompt_demands_pt_pt_and_sources():
    llm = FakeLLM([valid()])
    generate_proposals(make_topic("t1", context="CONTEXTO-XYZ"), llm)
    system, user = llm.calls[0]
    assert "PT-PT" in system and "fotorrealista" in system
    assert SID in user and "CONTEXTO-XYZ" in user


def test_revise_includes_feedback_and_keeps_variant():
    p = make_proposal("ab12cd34", topic=TOPIC, variant="B")
    llm = FakeLLM([json.dumps(variant("B"))])
    new = revise_proposal(p, TOPIC, "mais curto e mais ácido", llm)
    assert "mais curto e mais ácido" in llm.calls[0][1]
    assert (new.id, new.variant, new.topic_id) == ("ab12cd34", "B", "t1") and new.script_pt == "Piada B"


def test_revise_invalid_answer_raises():
    p = make_proposal("ab12cd34", topic=TOPIC)
    with pytest.raises(ProposalError):
        revise_proposal(p, TOPIC, "x", FakeLLM(["lixo"]))


def test_anthropic_client_joins_text_blocks_only():
    class Msgs:
        def create(self, **kw):
            self.kw = kw
            return SimpleNamespace(content=[SimpleNamespace(type="thinking", thinking="..."),
                                            SimpleNamespace(type="text", text="olá "),
                                            SimpleNamespace(type="text", text="mundo")])

    sdk = SimpleNamespace(messages=Msgs())
    out = AnthropicClient(sdk, "modelo-x").complete("sys", "user")
    assert out == "olá mundo"
    assert sdk.messages.kw["model"] == "modelo-x" and sdk.messages.kw["system"] == "sys"


def test_build_llm_needs_model_and_key():
    with pytest.raises(ValueError):
        build_llm({"ANTHROPIC_API_KEY": "k"})
    with pytest.raises(ValueError):
        build_llm({"LLM_MODEL": "m"})
    assert hasattr(build_llm({"LLM_MODEL": "m", "ANTHROPIC_API_KEY": "k"}), "complete")
