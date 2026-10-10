from datetime import date, timedelta

import pytest
from builders import make_proposal, make_topic
from fakes import FakePublisher
from onlinebusinesses.metrics import collect_insights, success, weekly_report
from onlinebusinesses.models import Insights
from onlinebusinesses.store import Store

START = date(2026, 10, 17)


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "t.sqlite")
    s.init()
    s.save_topics(START, [make_topic("t1")])
    s.save_proposals([make_proposal("aaaaaaaa", variant="A"), make_proposal("bbbbbbbb", variant="B")])
    return s


def publish_on(store, offsets, pid="aaaaaaaa"):
    for i in offsets:
        store.record_publication(f"{pid}-{i}", "instagram", f"ig-{i}", day=START + timedelta(days=i))


def test_success_when_published_every_day_without_interventions(store):
    publish_on(store, range(7))
    assert success(store, START)


def test_success_fails_when_a_day_has_no_publication(store):
    publish_on(store, [0, 1, 2, 4, 5, 6])
    assert not success(store, START)


def test_success_fails_when_ricardo_intervened(store):
    publish_on(store, range(7))
    store.record_decision("aaaaaaaa", "accept", START + timedelta(days=3))
    assert not success(store, START)


def test_decision_outside_the_window_does_not_count(store):
    publish_on(store, range(7))
    store.record_decision("aaaaaaaa", "accept", START - timedelta(days=1))
    assert success(store, START)


def test_weekly_report_compares_variants_per_topic(store):
    store.record_publication("aaaaaaaa", "instagram", "ig-a", day=START)
    store.record_publication("bbbbbbbb", "instagram", "ig-b", day=START)
    store.save_insights("aaaaaaaa", "instagram", Insights(100, 10, 3, 2, 4.5))
    store.save_insights("bbbbbbbb", "instagram", Insights(300, 20, 5, 1, 6.0))
    report = weekly_report(store, START)
    assert "2026-10-17: 2" in report and "Governo anuncia medida" in report
    a_line = next(l for l in report.splitlines() if l.strip().startswith("A:"))
    b_line = next(l for l in report.splitlines() if l.strip().startswith("B:"))
    assert "100" in a_line and "300" in b_line
    assert "Sucesso: não" in report


def test_collect_insights_stores_and_skips_unsupported_platforms(store):
    store.record_publication("aaaaaaaa", "instagram", "ig-a", day=START)
    store.record_publication("aaaaaaaa", "tiktok", "draft-1", day=START)

    class IG(FakePublisher):
        def insights(self, external_id):
            return Insights(7, 1, 0, 0, 2.0)

    class TT(FakePublisher):
        def insights(self, external_id):
            raise NotImplementedError

    assert collect_insights(store, {"instagram": IG(), "tiktok": TT()}) == 1
    assert store.insights_for("aaaaaaaa") == [("instagram", Insights(7, 1, 0, 0, 2.0))]


def test_collect_insights_survives_platform_errors(store):
    store.record_publication("aaaaaaaa", "instagram", "ig-a", day=START)

    class Broken(FakePublisher):
        def insights(self, external_id):
            raise OSError("rede")

    assert collect_insights(store, {"instagram": Broken()}) == 0
