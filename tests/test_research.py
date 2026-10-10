import json
from datetime import timedelta

from builders import NOW, make_source, make_topic, rss
from fakes import FakeLLM, FakeSearch
from onlinebusinesses.config import FeedConfig
from onlinebusinesses.research import (add_context, classify_topics, cluster_topics, corroborate,
                                       fetch_items, rank_topics)

TIERS = {"a.pt": 1, "b.com": 2, "c.org": 2}


FEEDS = [FeedConfig("Quebrado", "https://down.pt/rss"), FeedConfig("Lixo", "https://bad.pt/rss"),
         FeedConfig("Bom", "https://www.b.com/rss")]


def test_fetch_skips_failing_feed_and_invalid_xml():
    good = rss([("Governo aprova lei", "https://www.b.com/n/1", NOW - timedelta(hours=2))])

    def http(url):
        if "down" in url:
            raise OSError("boom")
        return "<<<nao e xml" if "bad" in url else good

    items = fetch_items(FEEDS, TIERS, http, NOW)
    assert [(i.domain, i.title, i.tier) for i in items] == [("b.com", "Governo aprova lei", 2)]


def test_fetch_drops_old_items():
    xml = rss([("Velho", "https://b.com/n/1", NOW - timedelta(hours=48)),
               ("Novo", "https://b.com/n/2", NOW - timedelta(hours=1))])
    items = fetch_items([FeedConfig("B", "https://b.com/rss")], TIERS, lambda u: xml, NOW)
    assert [i.title for i in items] == ["Novo"]


def test_same_domain_is_one_source():
    items = [make_source("a.pt", 1, "Governo aprova nova lei da habitação", "s1"),
             make_source("a.pt", 1, "Governo aprova nova lei da habitação hoje", "s2")]
    assert cluster_topics(items) == []


def test_tier3_does_not_count():
    items = [make_source("a.pt", 1, "Governo aprova nova lei da habitação", "s1"),
             make_source("blog.example", 3, "Governo aprova nova lei da habitação", "s2")]
    assert cluster_topics(items) == []


def test_cluster_two_trusted_domains_makes_topic():
    items = [make_source("a.pt", 1, "Governo aprova nova lei da habitação", "s1"),
             make_source("b.com", 2, "Nova lei da habitação aprovada pelo Governo", "s2"),
             make_source("c.org", 2, "Final da Taça de Portugal adiada", "s3")]
    topics = cluster_topics(items)
    assert len(topics) == 1
    assert {s.domain for s in topics[0].sources} == {"a.pt", "b.com"}
    assert (topics[0].category, topics[0].travels, topics[0].context) == ("other", False, "")


def test_corroborate_adds_trusted_sources_only():
    topic = make_topic(sources=[make_source("a.pt", 1, sid="s1"), make_source("b.com", 2, sid="s2")])
    found = [make_source("c.org", 3, "x", "s3"), make_source("blog.example", 3, "y", "s4")]
    search = FakeSearch(found)
    out = corroborate(topic, search, TIERS, NOW)
    assert search.queries == [topic.title]
    assert {s.domain for s in out.sources} == {"a.pt", "b.com", "c.org"}  # c.org está em TIERS (nível 2)
    assert all(s.tier <= 2 for s in out.sources)


def test_corroborate_survives_search_failure():
    topic = make_topic()
    assert corroborate(topic, FakeSearch(error=RuntimeError("down")), TIERS, NOW) == topic


def test_add_context_uses_only_trusted_sources():
    topic = make_topic(sources=[make_source("blog.example", 3, sid="s0"),
                                make_source("a.pt", 1, sid="s1"), make_source("b.com", 2, sid="s2")])
    fetched = []

    def http(url):
        fetched.append(url)
        return "<html><body><p>Texto da notícia</p></body></html>"

    out = add_context(topic, http, max_chars=10)
    assert not any("blog.example" in u for u in fetched)
    assert out.context == "Texto da n"


def test_rank_prefers_more_trusted_domains():
    two = make_topic("two", [make_source("a.pt", 1, sid="1"), make_source("b.com", 2, sid="2")])
    three = make_topic("three", [make_source(d, 2, sid=d) for d in ("a.pt", "b.com", "c.org")])
    assert [t.id for t in rank_topics([two, three], n=1)] == ["three"]


def test_classify_sets_category_and_travels():
    llm = FakeLLM([json.dumps({"category": "ai", "travels": True})])
    out = classify_topics([make_topic(category="other", travels=False)], llm)
    assert (out[0].category, out[0].travels) == ("ai", True)


def test_classify_invalid_json_falls_back():
    out = classify_topics([make_topic(category="ai", travels=True)], FakeLLM(["isto não é json"]))
    assert (out[0].category, out[0].travels) == ("other", False)
