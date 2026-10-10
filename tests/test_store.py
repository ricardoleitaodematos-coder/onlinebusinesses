from datetime import date, datetime, timedelta, timezone

import pytest
from builders import make_proposal, make_topic
from onlinebusinesses.store import Store

DAY = date(2026, 10, 10)


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "t.sqlite")
    s.init()
    return s


def test_topics_roundtrip_in_order(store):
    ts = [make_topic("t1"), make_topic("t2")]
    store.save_topics(DAY, ts)
    assert store.topics(DAY) == ts
    assert store.topics(date(2026, 10, 11)) == []


def test_save_choice_overwrites_same_day(store):
    store.save_choice(DAY, ["t1", "t2"])
    store.save_choice(DAY, ["t2", "t3"])
    assert store.choice(DAY) == ["t2", "t3"]
    assert store.choice(date(2026, 10, 11)) == []


def test_proposals_and_status(store):
    a, b = make_proposal("aaaaaaaa", variant="A"), make_proposal("bbbbbbbb", variant="B")
    store.save_proposals([b, a])
    assert store.proposals_for("t1") == [a, b]
    assert store.status("aaaaaaaa") == "draft"
    store.set_status("aaaaaaaa", "rejected", ["morreu"])
    assert store.status("aaaaaaaa") == "rejected"
    assert store.reasons("aaaaaaaa") == ["morreu"]


def test_publication_is_none_then_id(store):
    store.save_proposals([make_proposal()])
    assert store.publication("ab12cd34", "instagram") is None
    store.record_publication("ab12cd34", "instagram", "ig-1")
    assert store.publication("ab12cd34", "instagram") == "ig-1"
    assert store.publication("ab12cd34", "tiktok") is None


def test_set_first_day_keeps_first_value(store):
    assert store.first_day() is None
    store.set_first_day(DAY)
    store.set_first_day(date(2026, 10, 20))
    assert store.first_day() == DAY


def test_offset_defaults_to_zero_and_persists(store):
    assert store.get_offset() == 0
    store.set_offset(42)
    assert store.get_offset() == 42


def test_bump_revision_counts_up_and_replace_proposal(store):
    p = make_proposal()
    store.save_proposals([p])
    assert [store.bump_revision(p.id) for _ in range(3)] == [1, 2, 3]
    new = make_proposal(script="Novo texto.")
    store.replace_proposal(new)
    assert store.proposals_for("t1") == [new]


def test_awaiting_feedback_set_and_clear(store):
    assert store.awaiting_feedback() is None
    store.set_awaiting_feedback("ab12cd34")
    assert store.awaiting_feedback() == "ab12cd34"
    store.set_awaiting_feedback(None)
    assert store.awaiting_feedback() is None


def test_selection_is_per_day_and_defaults_empty(store):
    assert store.selection(DAY) == []
    store.set_selection(DAY, [1, 3])
    assert store.selection(DAY) == [1, 3]
    assert store.selection(date(2026, 10, 11)) == []


def test_lookup_helpers(store):
    t, a = make_topic("t1"), make_proposal("aaaaaaaa", variant="A")
    store.save_topics(DAY, [t])
    store.save_proposals([a, make_proposal("bbbbbbbb", variant="B")])
    assert store.topic("t1") == t and store.proposal("aaaaaaaa") == a
    store.set_status("aaaaaaaa", "approved")
    assert store.proposals_by_status("approved") == [a]
    assert [p.id for p in store.proposals_by_status("draft")] == ["bbbbbbbb"]
    with pytest.raises(KeyError):
        store.proposal("nope")


def test_first_publication_day_is_the_earliest_dated_publication(store):
    assert store.first_publication_day() is None
    store.record_publication("p1", "instagram", "x")  # sem dia: não conta
    assert store.first_publication_day() is None
    store.record_publication("p2", "instagram", "y", date(2026, 10, 12))
    store.record_publication("p3", "instagram", "z", date(2026, 10, 15))
    assert store.first_publication_day() == date(2026, 10, 12)


def test_topic_day_and_status_at(store):
    store.save_topics(DAY, [make_topic("t1")])
    assert store.topic_day("t1") == DAY
    with pytest.raises(KeyError):
        store.topic_day("nope")
    store.save_proposals([make_proposal()])
    at = datetime(2026, 10, 10, 8, 0, tzinfo=timezone.utc)
    store.set_status("ab12cd34", "gated", at=at)
    assert store.status_at("ab12cd34") == at
    store.set_status("ab12cd34", "expired", at=at + timedelta(hours=1))
    assert store.status("ab12cd34") == "expired" and store.status_at("ab12cd34") == at + timedelta(hours=1)


def test_claim_publication_is_exclusive_until_released_or_stale(store):
    t = datetime(2026, 10, 10, 8, 0, tzinfo=timezone.utc)
    assert store.claim_publication("p1", "instagram", t)
    assert not store.claim_publication("p1", "instagram", t + timedelta(minutes=30))
    assert store.claim_publication("p1", "tiktok", t)
    assert store.claim_publication("p1", "instagram", t + timedelta(minutes=61))  # reserva parada há > 60 min
    store.release_claim("p1", "instagram")
    assert store.claim_publication("p1", "instagram", t + timedelta(minutes=62))
    store.record_publication("p1", "instagram", "ig-1")
    store.release_claim("p1", "instagram")
    assert not store.claim_publication("p1", "instagram", t + timedelta(hours=5))  # já publicada


def test_set_status_if_only_changes_expected_states(store):
    store.save_proposals([make_proposal()])
    store.set_status("ab12cd34", "rejected", ["recusada"])
    assert not store.set_status_if("ab12cd34", ("approved", "gated"), "published")
    assert store.status("ab12cd34") == "rejected" and store.reasons("ab12cd34") == ["recusada"]
    store.set_status("ab12cd34", "approved")
    assert store.set_status_if("ab12cd34", ("approved", "gated"), "published")
    assert store.status("ab12cd34") == "published"
