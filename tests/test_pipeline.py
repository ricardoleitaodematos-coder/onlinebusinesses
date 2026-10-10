import json
import re
from datetime import date, timedelta

import pytest
from builders import NOW, make_proposal, make_source, make_topic, rss
from fakes import FakeChannel, FakeLLM, FakePublisher, FakeSearch, fake_builder
from onlinebusinesses.brief import Feedback, ProposalDecision, TopicsChosen
from onlinebusinesses.config import load_settings
from onlinebusinesses.pipeline import Pipeline, caption_for
from onlinebusinesses.store import Store

DAY = date(2026, 10, 10)
WEEK2 = NOW + timedelta(days=8)
LATER = NOW + timedelta(hours=3)  # depois da janela de revisão (publish_hold_minutes = 120)
SRC = (make_source("a.pt", 1, sid="s1"), make_source("b.com", 2, sid="s2"))
BLOCK = {"pt": ["morreu"]}


def proposals_json(script_a="Piada A", script_b="Piada B", cite="s1"):
    def one(v, script):
        return {"variant": v, "script_pt": script, "claims": [{"text": "facto", "source_ids": [cite]}],
                "visual_prompts": ["cartoon de um robô"], "visual_style": "cartoon"}
    return json.dumps({"proposals": [one("A", script_a), one("B", script_b)]})


def revision_json(script="Piada revista"):
    return json.dumps({"script_pt": script, "claims": [{"text": "facto", "source_ids": ["s1"]}],
                       "visual_prompts": ["cartoon"], "visual_style": "cartoon"})


@pytest.fixture
def env(tmp_path):
    def make(llm_responses=(), events=(), publishers=None, seed_topics=True):
        settings = load_settings({"DB_PATH": str(tmp_path / "db.sqlite"), "FEEDS_PATH": str(tmp_path / "feeds.toml"),
                                  "OUT_DIR": str(tmp_path / "out")})
        store = Store(settings.db_path)
        store.init()
        if seed_topics:
            store.save_topics(DAY, [make_topic("t1", SRC), make_topic("t2", SRC), make_topic("t3", SRC)])
        channel = FakeChannel(events)
        llm = FakeLLM(list(llm_responses) or [proposals_json()])
        pubs = {"instagram": FakePublisher()} if publishers is None else publishers
        pipe = Pipeline(store, channel, llm, FakeSearch(), None, None, pubs, settings, lambda url: "",
                        BLOCK, {"a.pt": 1, "b.com": 2}, tmp_path / "work", builder=fake_builder)
        return pipe, store, channel, llm, pubs
    return make


def choose(*ids):
    return TopicsChosen(DAY, tuple(ids))


# --- pesquisa -------------------------------------------------------------------------------------------------

def test_research_sends_topics_once_and_sets_first_day(tmp_path, env):
    pipe, store, channel, llm, _ = env(['{"category": "ai", "travels": true}'], seed_topics=False)
    (tmp_path / "feeds.toml").write_text('[[feed]]\noutlet = "A"\nurl = "https://a.pt/rss"\n'
                                         '[[feed]]\noutlet = "B"\nurl = "https://b.com/rss"\n', encoding="utf-8")
    feeds = {"https://a.pt/rss": rss([("Governo aprova nova lei da habitação", "https://a.pt/n/1", NOW)]),
             "https://b.com/rss": rss([("Nova lei da habitação aprovada pelo Governo", "https://b.com/n/1", NOW)])}
    pipe.http = lambda url: feeds[url]
    topics = pipe.stage_research(NOW)
    assert len(topics) == 1 and topics[0].category == "ai" and topics[0].travels
    assert len(channel.topics_sent) == 1 and store.first_day() == DAY
    pipe.stage_research(NOW)  # o cron volta a correr: não repete o envio
    assert len(channel.topics_sent) == 1


def test_research_survives_search_failure(tmp_path, env):
    pipe, _, channel, _, _ = env(['{"category": "other", "travels": false}'], seed_topics=False)
    (tmp_path / "feeds.toml").write_text('[[feed]]\noutlet = "A"\nurl = "https://a.pt/rss"\n'
                                         '[[feed]]\noutlet = "B"\nurl = "https://b.com/rss"\n', encoding="utf-8")
    feeds = {"https://a.pt/rss": rss([("Governo aprova nova lei da habitação", "https://a.pt/n/1", NOW)]),
             "https://b.com/rss": rss([("Nova lei da habitação aprovada pelo Governo", "https://b.com/n/1", NOW)])}
    pipe.http = lambda url: feeds[url]
    pipe.search.error = RuntimeError("pesquisa em baixo")
    assert len(pipe.stage_research(NOW)) == 1


class RoutingLLM:
    """Classifica temas e gera propostas conforme o pedido."""

    def __init__(self):
        self.calls = []

    def complete(self, system, user):
        self.calls.append((system, user))
        if system.startswith("Classifica"):
            return '{"category": "ai", "travels": true}'
        return proposals_json(cite=re.search(r"id=(\w+)", user).group(1))


TWO_TOPIC_FEEDS = {
    "https://a.pt/rss": rss([("Governo aprova nova lei da habitação", "https://a.pt/n/1", NOW),
                             ("Parlamento debate orçamento do Estado para 2027", "https://a.pt/n/2", NOW)]),
    "https://b.com/rss": rss([("Nova lei da habitação aprovada pelo Governo", "https://b.com/n/1", NOW),
                              ("Orçamento do Estado para 2027 debatido no Parlamento", "https://b.com/n/2", NOW)])}


def research_ready(tmp_path, pipe, feeds=TWO_TOPIC_FEEDS):
    (tmp_path / "feeds.toml").write_text('[[feed]]\noutlet = "A"\nurl = "https://a.pt/rss"\n'
                                         '[[feed]]\noutlet = "B"\nurl = "https://b.com/rss"\n', encoding="utf-8")
    pipe.http = lambda url: feeds.get(url, "")
    pipe.llm = RoutingLLM()


def test_same_articles_on_two_days_get_new_topic_and_proposal_ids(tmp_path, env):
    pipe, store, channel, _, _ = env(seed_topics=False)
    research_ready(tmp_path, pipe)
    day1 = pipe.stage_research(NOW)
    assert len(day1) == 2
    channel.events = [TopicsChosen(DAY, tuple(t.id for t in day1))]
    pipe.stage_poll(NOW)
    old = store.proposals_for(day1[0].id)[0]
    channel.events = [ProposalDecision(old.id, "reject")]
    pipe.stage_poll(NOW)
    later = NOW + timedelta(days=1)
    day2 = pipe.stage_research(later)
    assert {t.id for t in day2}.isdisjoint({t.id for t in day1})
    channel.events = [TopicsChosen(DAY + timedelta(days=1), tuple(t.id for t in day2))]
    pipe.stage_poll(later)
    new_ids = {p.id for t in day2 for p in store.proposals_for(t.id)}
    assert len(new_ids) == 4 and old.id not in new_ids
    assert store.status(old.id) == "rejected"


def test_research_discards_topics_with_blocked_words(tmp_path, env):
    pipe, store, channel, _, _ = env(seed_topics=False)
    feeds = {"https://a.pt/rss": rss([("Governo aprova nova lei da habitação", "https://a.pt/n/1", NOW),
                                      ("Ataque faz 20 mortos em Lisboa", "https://a.pt/n/2", NOW)]),
             "https://b.com/rss": rss([("Nova lei da habitação aprovada pelo Governo", "https://b.com/n/1", NOW),
                                       ("Em Lisboa ataque faz 20 mortos", "https://b.com/n/2", NOW)])}
    research_ready(tmp_path, pipe, feeds)
    pipe.blocklist = {"pt": ["ataque", "mortos"]}
    topics = pipe.stage_research(NOW)
    assert [t.title for t in topics] == ["Governo aprova nova lei da habitação"]
    assert [t.title for t in channel.topics_sent[0][1]] == ["Governo aprova nova lei da habitação"]
    assert any("1" in n and "descart" in n.lower() for n in channel.notes)


def test_caption_with_blocked_word_rejects_proposal(env, monkeypatch):
    import onlinebusinesses.pipeline as pipeline_module

    pipe, store, channel, _, _ = env(events=[choose("t1", "t2")])
    monkeypatch.setattr(pipeline_module, "caption_for", lambda p, t: "Ele morreu.\n\nConteúdo satírico gerado com IA.")
    pipe.stage_poll(NOW)
    assert channel.proposals_sent == []
    assert all(store.status(p.id) == "rejected" for p in store.proposals_for("t1"))


# --- escolha e geração ------------------------------------------------------------------------------------------

def test_no_choice_generates_and_publishes_nothing(env):
    pipe, store, channel, llm, pubs = env()
    pipe.stage_poll(NOW)
    assert pipe.stage_publish(WEEK2) == {}
    assert store.proposals_for("t1") == [] and llm.calls == [] and pubs["instagram"].calls == []


def test_choice_makes_four_proposals_per_two_topics(env):
    pipe, store, channel, llm, _ = env(events=[choose("t1", "t2")])
    pipe.stage_poll(NOW)
    assert len(store.proposals_for("t1")) == 2 and len(store.proposals_for("t2")) == 2
    assert len(channel.proposals_sent) == 4 and store.proposals_for("t3") == []
    assert {store.status(p.id) for p in channel.proposals_sent} == {"gated"}


def test_late_choice_of_yesterdays_topics_generates_nothing(env):
    pipe, store, channel, llm, _ = env(events=[choose("t1", "t2")])
    tomorrow = NOW + timedelta(days=1)
    pipe.stage_poll(tomorrow)
    assert store.proposals_for("t1") == [] and llm.calls == [] and store.choice(DAY) == []
    assert any("2026-10-10" in n and "espera" in n for n in channel.notes)
    assert channel.polled_at == tomorrow


def test_choice_with_wrong_count_is_ignored(env):
    pipe, store, channel, _, _ = env(events=[choose("t1")])
    pipe.stage_poll(NOW)
    assert store.proposals_for("t1") == [] and channel.notes


def test_same_choice_twice_generates_once(env):
    pipe, store, channel, llm, _ = env(events=[choose("t1", "t2"), choose("t1", "t2")])
    pipe.stage_poll(NOW)
    assert len(llm.calls) == 2 and len(channel.proposals_sent) == 4


def test_rejected_by_gates_is_never_published_and_ricardo_is_told_why(env):
    pipe, store, channel, _, pubs = env([proposals_json("Ele morreu ontem.", "Piada B")], events=[choose("t1", "t2")])
    pipe.stage_poll(NOW)
    bad = [p for p in store.proposals_for("t1") if p.variant == "A"][0]
    assert store.status(bad.id) == "rejected" and "morreu" in " ".join(store.reasons(bad.id))
    assert any("morreu" in n for n in channel.notes) and bad not in channel.proposals_sent
    pipe.stage_publish(WEEK2)
    assert all(c[3] != bad.id for c in pubs["instagram"].calls)


def test_third_party_asset_rejects_after_production(env, monkeypatch):
    pipe, store, channel, _, _ = env(events=[choose("t1", "t2")])
    from onlinebusinesses.models import Asset

    def builder(p, lang, voice, visuals, llm, workdir):
        path, _ = fake_builder(p, lang, voice, visuals, llm, workdir)
        return path, [Asset("musica.mp3", "third-party", None)]

    pipe.builder = builder
    pipe.stage_poll(NOW)
    assert channel.proposals_sent == [] and "terceiros" in " ".join(store.reasons(store.proposals_for("t1")[0].id))


def test_llm_failure_is_reported_not_raised(env):
    pipe, store, channel, _, _ = env(["lixo"], events=[choose("t1", "t2")])
    pipe.stage_poll(NOW)
    assert channel.proposals_sent == [] and len(channel.notes) == 2


# --- decisões ------------------------------------------------------------------------------------------------------

def first_proposal(store):
    return store.proposals_for("t1")[0]


def test_accept_then_publish(env):
    pipe, store, channel, _, pubs = env(events=[choose("t1", "t2")])
    pipe.stage_poll(NOW)
    p = first_proposal(store)
    channel.events = [ProposalDecision(p.id, "accept")]
    pipe.stage_poll(NOW)
    assert store.status(p.id) == "approved"
    out = pipe.stage_publish(NOW)
    assert out == {f"{p.id}:instagram": "ext-1"} and store.status(p.id) == "published"
    video, caption, ai_label, key = pubs["instagram"].calls[0]
    assert video.name == f"{p.id}-pt-PT.mp4" and ai_label is True and key == p.id and "IA" in caption


def past_acceptance(store):
    """A primeira publicação foi há 8 dias: o período de aceitação obrigatória já acabou."""
    store.record_publication("antiga", "instagram", "ig-0", DAY - timedelta(days=8))


def test_reject_never_publishes(env):
    pipe, store, channel, _, pubs = env(events=[choose("t1", "t2")])
    past_acceptance(store)
    pipe.stage_poll(NOW)
    p = first_proposal(store)
    channel.events = [ProposalDecision(p.id, "reject")]
    pipe.stage_poll(NOW)
    assert store.status(p.id) == "rejected"
    assert len(pipe.stage_publish(LATER)) == 3  # as outras três propostas saem; a recusada não
    assert all(c[3] != p.id for c in pubs["instagram"].calls)


def test_improve_asks_feedback_then_revises_and_resends(env):
    pipe, store, channel, _, _ = env([proposals_json(), revision_json()], events=[choose("t1", "t2")])
    pipe.stage_poll(NOW)
    p = first_proposal(store)
    channel.events = [ProposalDecision(p.id, "improve")]
    pipe.stage_poll(NOW)
    assert channel.feedback_asked == [p.id] and store.status(p.id) == "revising"
    sent_before = len(channel.proposals_sent)
    channel.events = [Feedback(p.id, "mais curto")]
    pipe.stage_poll(NOW)
    assert store.proposal(p.id).script_pt == "Piada revista" and store.status(p.id) == "gated"
    assert len(channel.proposals_sent) == sent_before + 1


def test_fourth_revision_rejects(env):
    pipe, store, channel, _, _ = env([proposals_json()] + [revision_json()] * 4, events=[choose("t1", "t2")])
    pipe.stage_poll(NOW)
    p = first_proposal(store)
    for i in range(4):
        channel.events = [ProposalDecision(p.id, "improve")]
        pipe.stage_poll(NOW)
        channel.events = [Feedback(p.id, f"pedido {i}")]
        pipe.stage_poll(NOW)
    assert store.status(p.id) == "rejected"


def test_failed_revision_keeps_proposal_and_tells_ricardo(env):
    pipe, store, channel, _, _ = env([proposals_json(), "lixo"], events=[choose("t1", "t2")])
    pipe.stage_poll(NOW)
    p = first_proposal(store)
    channel.events = [ProposalDecision(p.id, "improve")]
    pipe.stage_poll(NOW)
    channel.events = [Feedback(p.id, "x")]
    pipe.stage_poll(NOW)
    assert store.status(p.id) == "gated" and store.proposal(p.id).script_pt == "Piada A"


# --- publicação ------------------------------------------------------------------------------------------------------

def test_first_week_requires_accept_and_week_two_publishes_gated(env):
    pipe, store, channel, _, pubs = env(events=[choose("t1", "t2")])
    store.record_publication("antiga", "instagram", "ig-0", DAY)  # 1.ª publicação hoje: começa o período
    pipe.stage_poll(NOW)
    assert pipe.stage_publish(LATER) == {}
    later_day = DAY + timedelta(days=8)
    store.save_topics(later_day, [make_topic("u1", SRC), make_topic("u2", SRC)])
    channel.events = [TopicsChosen(later_day, ("u1", "u2"))]
    pipe.stage_poll(WEEK2)
    out = pipe.stage_publish(WEEK2 + timedelta(hours=3))
    assert len(out) == 4 and {pid.split(":")[0] for pid in out} == {p.id for t in ("u1", "u2")
                                                                    for p in store.proposals_for(t)}


def test_publish_twice_does_not_duplicate(env):
    pipe, store, channel, _, pubs = env(events=[choose("t1", "t2")])
    past_acceptance(store)
    pipe.stage_poll(NOW)
    pipe.stage_publish(LATER)
    assert pipe.stage_publish(LATER) == {} and len(pubs["instagram"].calls) == 4


def test_acceptance_clock_starts_at_first_publication_not_first_research(env):
    pipe, store, channel, _, pubs = env(events=[choose("t1", "t2")])
    store.set_first_day(DAY - timedelta(days=30))  # pesquisa há um mês, mas nunca se publicou nada
    pipe.stage_poll(NOW)
    assert pipe.stage_publish(LATER) == {} and pubs["instagram"].calls == []


def test_ignored_backlog_is_expired_not_published_in_bulk(env):
    pipe, store, channel, _, pubs = env(seed_topics=False)
    store.set_first_day(DAY - timedelta(days=9))
    past_acceptance(store)
    old = []
    for i in range(1, 8):  # 7 dias de propostas que passaram nas barreiras e o Ricardo ignorou
        topic = make_topic(f"old{i}", SRC)
        store.save_topics(DAY - timedelta(days=i), [topic])
        p = make_proposal(f"old{i:05d}", topic=topic)
        store.save_proposals([p])
        store.set_status(p.id, "gated", at=NOW - timedelta(days=i))
        old.append(p.id)
    assert pipe.stage_publish(NOW) == {} and pubs["instagram"].calls == []
    assert {store.status(pid) for pid in old} == {"expired"}
    assert pipe.stage_publish(LATER) == {}


def test_gated_waits_for_the_review_window_before_auto_publishing(env):
    pipe, store, channel, _, pubs = env(events=[choose("t1", "t2")])
    past_acceptance(store)
    pipe.stage_poll(NOW)
    assert pipe.stage_publish(NOW + timedelta(minutes=119)) == {}
    assert len(pipe.stage_publish(NOW + timedelta(minutes=121))) == 4


def test_same_decision_event_twice_does_not_duplicate(env):
    pipe, store, channel, _, pubs = env(events=[choose("t1", "t2")])
    pipe.stage_poll(NOW)
    p = first_proposal(store)
    channel.events = [ProposalDecision(p.id, "accept"), ProposalDecision(p.id, "accept")]
    pipe.stage_poll(NOW)
    pipe.stage_publish(NOW)
    pipe.stage_publish(NOW)
    assert [c[3] for c in pubs["instagram"].calls] == [p.id]


def test_publisher_failure_leaves_status_unpublished_and_retries_safely(env):
    flaky = FakePublisher(fail_times=1)
    pipe, store, channel, _, _ = env(events=[choose("t1", "t2")], publishers={"instagram": flaky})
    pipe.stage_poll(NOW)
    p = first_proposal(store)
    channel.events = [ProposalDecision(p.id, "accept")]
    pipe.stage_poll(NOW)
    assert pipe.stage_publish(NOW) == {} and store.status(p.id) == "approved"
    assert any("falhou" in n for n in channel.notes)
    assert pipe.stage_publish(NOW) == {f"{p.id}:instagram": "ext-2"} and store.status(p.id) == "published"
    assert pipe.stage_publish(NOW) == {} and len(flaky.calls) == 2


def test_overlapping_runs_on_the_same_database_publish_once(env):
    pipe, store, channel, _, _ = env(events=[choose("t1", "t2")], publishers={})
    pipe.stage_poll(NOW)
    p = first_proposal(store)
    channel.events = [ProposalDecision(p.id, "accept")]
    pipe.stage_poll(NOW)
    other_pub = FakePublisher()
    other, *_ = env(seed_topics=False, publishers={"instagram": other_pub})

    class SlowUpload(FakePublisher):
        def publish(self, *args):
            other.stage_publish(NOW)  # outra execução do cron arranca a meio do upload
            return super().publish(*args)

    slow = SlowUpload()
    pipe.publishers = {"instagram": slow}
    pipe.stage_publish(NOW)
    assert len(slow.calls) + len(other_pub.calls) == 1
    assert store.status(p.id) == "published"


def test_failed_upload_releases_the_reservation(env):
    flaky = FakePublisher(fail_times=1)
    pipe, store, channel, _, _ = env(events=[choose("t1", "t2")], publishers={"instagram": flaky})
    pipe.stage_poll(NOW)
    p = first_proposal(store)
    channel.events = [ProposalDecision(p.id, "accept")]
    pipe.stage_poll(NOW)
    pipe.stage_publish(NOW)
    assert store.claim_publication(p.id, "instagram", NOW)


def test_reject_during_upload_stops_other_platforms_and_is_never_overwritten(env):
    pipe, store, channel, _, _ = env(events=[choose("t1", "t2")], publishers={})
    pipe.stage_poll(NOW)
    p = first_proposal(store)
    channel.events = [ProposalDecision(p.id, "accept")]
    pipe.stage_poll(NOW)
    other, _, other_channel, _, _ = env(seed_topics=False, publishers={})

    class RejectedMeanwhile(FakePublisher):
        def publish(self, *args):
            other_channel.events = [ProposalDecision(p.id, "reject")]
            other.stage_poll(NOW)  # o poll trata o «Recusar» enquanto o upload decorre
            return super().publish(*args)

    tiktok = FakePublisher()
    pipe.publishers = {"instagram": RejectedMeanwhile(), "tiktok": tiktok}
    pipe.stage_publish(NOW)
    assert tiktok.calls == [] and store.status(p.id) == "rejected"


def test_reject_during_last_upload_keeps_rejected(env):
    pipe, store, channel, _, _ = env(events=[choose("t1", "t2")], publishers={})
    pipe.stage_poll(NOW)
    p = first_proposal(store)
    channel.events = [ProposalDecision(p.id, "accept")]
    pipe.stage_poll(NOW)

    class RejectedMeanwhile(FakePublisher):
        def publish(self, *args):
            store.set_status(p.id, "rejected", ["recusada pelo Ricardo"])
            return super().publish(*args)

    pipe.publishers = {"instagram": RejectedMeanwhile()}
    pipe.stage_publish(NOW)
    assert store.status(p.id) == "rejected" and store.publication(p.id, "instagram")


def test_revision_stays_revising_until_the_new_video_is_built(env):
    pipe, store, channel, _, _ = env([proposals_json(), revision_json()], events=[choose("t1", "t2")])
    pipe.stage_poll(NOW)
    p = first_proposal(store)
    channel.events = [ProposalDecision(p.id, "improve")]
    pipe.stage_poll(NOW)
    seen = []

    def builder(prop, lang, voice, visuals, llm, workdir):
        seen.append(store.status(prop.id))
        return fake_builder(prop, lang, voice, visuals, llm, workdir)

    pipe.builder = builder
    channel.events = [Feedback(p.id, "mais curto")]
    pipe.stage_poll(NOW)
    assert seen == ["revising"] and store.status(p.id) == "gated"


def test_proposal_is_published_only_when_every_platform_succeeded(env):
    tiktok = FakePublisher(fail_times=1)
    pipe, store, channel, _, pubs = env(events=[choose("t1", "t2")],
                                        publishers={"instagram": FakePublisher(), "tiktok": tiktok})
    pipe.stage_poll(NOW)
    p = first_proposal(store)
    channel.events = [ProposalDecision(p.id, "accept")]
    pipe.stage_poll(NOW)
    pipe.stage_publish(NOW)
    assert store.status(p.id) == "approved" and store.publication(p.id, "instagram")
    pipe.stage_publish(NOW)
    assert store.status(p.id) == "published" and len(pubs["instagram"].calls) == 1


def test_caption_uses_the_script_hook_not_the_raw_headline():
    t = make_topic()
    p = make_proposal(topic=t, script="O Governo descobriu a roda. Depois inventou o IVA da roda.")
    c = caption_for(p, t)
    assert c.startswith("O Governo descobriu a roda.\n\nConteúdo satírico gerado com IA. Fontes: ")
    assert t.title not in c and "inventou" not in c and "a.pt" in c


def test_decisions_and_publication_day_are_recorded_for_metrics(env):
    pipe, store, channel, _, _ = env(events=[choose("t1", "t2")])
    pipe.stage_poll(NOW)
    p = first_proposal(store)
    channel.events = [ProposalDecision(p.id, "accept")]
    pipe.stage_poll(NOW)
    pipe.stage_publish(NOW)
    assert store.decisions_between(DAY, DAY) == 1
    assert [(pid, plat, day) for pid, plat, _, day in store.publications_between(DAY, DAY)] == [(p.id, "instagram", DAY)]
