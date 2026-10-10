from builders import make_proposal, make_topic
from onlinebusinesses.models import Asset, GateResult, Insights, Proposal, Topic


def test_topic_json_roundtrip():
    t = make_topic()
    assert Topic.from_json(t.to_json()) == t


def test_proposal_json_roundtrip():
    p = make_proposal()
    assert Proposal.from_json(p.to_json()) == p


def test_small_types_json_roundtrip():
    for obj in (Asset("a.mp4", "generated", None), GateResult(False, ("x",)), Insights(1, 2, 3, 4, 5.5)):
        assert type(obj).from_json(obj.to_json()) == obj
