from datetime import date, datetime, timedelta, timezone

from builders import make_proposal, make_source, make_topic
from fakes import FakeHttp
from onlinebusinesses.brief import (Feedback, ProposalDecision, TelegramChannel, TopicsChosen, render_proposal,
                                    render_topics)
from onlinebusinesses.store import Store

DAY = date(2026, 10, 10)
CHAT = 111


def cb(update_id, data, chat=CHAT, message_id=7):
    return {"update_id": update_id, "callback_query": {"id": f"cq{update_id}", "data": data,
            "message": {"message_id": message_id, "chat": {"id": chat}}}}


def msg(update_id, text, chat=CHAT):
    return {"update_id": update_id, "message": {"message_id": update_id, "text": text, "chat": {"id": chat}}}


def setup(tmp_path, updates=()):
    store = Store(tmp_path / "t.sqlite")
    store.init()
    topics = [make_topic(f"t{i}") for i in range(1, 6)]
    store.save_topics(DAY, topics)
    http = FakeHttp(updates)
    return store, topics, http, TelegramChannel(http, "TOKEN", CHAT, store)


def test_updates_from_other_chat_are_ignored(tmp_path):
    store, _, http, ch = setup(tmp_path, [cb(1, "p:ab12cd34:a", chat=999), msg(2, "olá", chat=999)])
    assert ch.poll() == []
    assert http.sent("sendMessage") == []


def test_confirm_with_two_selected_returns_topics_chosen(tmp_path):
    store, topics, http, ch = setup(tmp_path, [cb(1, "t:2026-10-10:2"), cb(2, "t:2026-10-10:4"), cb(3, "tc:2026-10-10")])
    assert ch.poll() == [TopicsChosen(DAY, ("t2", "t4"))]


def test_confirm_with_wrong_count_asks_for_exactly_two(tmp_path):
    store, _, http, ch = setup(tmp_path, [cb(1, "t:2026-10-10:2"), cb(2, "tc:2026-10-10")])
    assert ch.poll() == []
    assert "2" in http.sent("sendMessage")[-1]["text"]


def test_toggle_twice_unselects(tmp_path):
    store, _, http, ch = setup(tmp_path, [cb(1, "t:2026-10-10:2"), cb(2, "t:2026-10-10:2")])
    ch.poll()
    assert store.selection(DAY) == []


def test_decision_buttons_map_to_actions(tmp_path):
    ups = [cb(1, "p:ab12cd34:a"), cb(2, "p:ab12cd34:r"), cb(3, "p:ab12cd34:i")]
    _, _, _, ch = setup(tmp_path, ups)
    assert ch.poll() == [ProposalDecision("ab12cd34", "accept"), ProposalDecision("ab12cd34", "reject"),
                         ProposalDecision("ab12cd34", "improve")]


def test_double_press_is_idempotent(tmp_path):
    store, _, http, ch = setup(tmp_path, [cb(5, "p:ab12cd34:a")])
    assert len(ch.poll()) == 1
    assert store.get_offset() == 6
    assert ch.poll() == []  # o mesmo update_id volta a chegar: já tratado


def test_every_callback_is_answered(tmp_path):
    _, _, http, ch = setup(tmp_path, [cb(1, "p:ab12cd34:a")])
    ch.poll()
    assert [a["callback_query_id"] for a in http.sent("answerCallbackQuery")] == ["cq1"]


def test_free_text_after_improve_becomes_feedback(tmp_path):
    store, _, http, ch = setup(tmp_path, [msg(1, "mais curto")])
    store.set_awaiting_feedback("ab12cd34")
    assert ch.poll() == [Feedback("ab12cd34", "mais curto")]
    assert store.awaiting_feedback() is None


def test_free_text_without_pending_request_is_ignored(tmp_path):
    _, _, _, ch = setup(tmp_path, [msg(1, "olá")])
    assert ch.poll() == []


def test_ask_feedback_sets_pending_and_prompts(tmp_path):
    store, _, http, ch = setup(tmp_path)
    ch.ask_feedback("ab12cd34")
    assert store.awaiting_feedback() == "ab12cd34"
    assert len(http.sent("sendMessage")) == 1


def test_sent_keyboards_fit_callback_limit_and_have_three_buttons(tmp_path):
    store, topics, http, ch = setup(tmp_path)
    ch.send_topics(DAY, topics)
    ch.send_proposal(make_proposal(), topics[0])
    for payload in http.sent("sendMessage"):
        for row in payload["reply_markup"]["inline_keyboard"]:
            for b in row:
                assert len(b["callback_data"].encode()) <= 64
    labels = [b["text"] for row in http.sent("sendMessage")[-1]["reply_markup"]["inline_keyboard"] for b in row]
    assert labels == ["Aceitar", "Recusar", "Melhorar"]


def test_render_topics_lists_all_titles_and_urls():
    ts = [make_topic(f"t{i}", [make_source("a.pt", 1, sid=f"x{i}"), make_source("b.com", 2, sid=f"y{i}")])
          for i in range(1, 4)]
    text = render_topics(DAY, ts)
    assert text.count("Governo anuncia medida") == 3
    assert "https://a.pt/n/1" in text and "1." in text and "3." in text


def test_render_proposal_shows_script_and_claim_sources():
    t = make_topic()
    p = make_proposal(topic=t, script="Piada sobre a medida.")
    text = render_proposal(p, t)
    assert "Piada sobre a medida." in text and "facto" in text and t.sources[0].url in text


TOMORROW = datetime(2026, 10, 11, 8, 0, tzinfo=timezone.utc)


def test_selection_taps_on_yesterdays_topics_are_refused(tmp_path):
    store, _, http, ch = setup(tmp_path, [cb(1, "t:2026-10-10:2"), cb(2, "tc:2026-10-10")])
    assert ch.poll(TOMORROW) == []
    assert store.selection(DAY) == [] and http.sent("editMessageReplyMarkup") == []
    assert any("2026-10-10" in m["text"] and "espera" in m["text"] for m in http.sent("sendMessage"))


def test_selection_taps_on_todays_topics_work_with_now(tmp_path):
    today = datetime(2026, 10, 10, 8, 0, tzinfo=timezone.utc)
    store, topics, http, ch = setup(tmp_path, [cb(1, "t:2026-10-10:2"), cb(2, "t:2026-10-10:4"),
                                               cb(3, "tc:2026-10-10")])
    assert ch.poll(today) == [TopicsChosen(DAY, ("t2", "t4"))]


def test_proposal_buttons_carry_the_current_revision(tmp_path):
    store, topics, http, ch = setup(tmp_path)
    p = make_proposal()
    store.save_proposals([p])
    store.bump_revision(p.id)
    ch.send_proposal(p, topics[0])
    data = [b["callback_data"] for b in http.sent("sendMessage")[-1]["reply_markup"]["inline_keyboard"][0]]
    assert data == [f"p:{p.id}:a:1", f"p:{p.id}:r:1", f"p:{p.id}:i:1"]


def test_decision_with_revision_is_parsed_and_old_format_still_works(tmp_path):
    _, _, _, ch = setup(tmp_path, [cb(1, "p:ab12cd34:a:2"), cb(2, "p:ab12cd34:r")])
    assert ch.poll() == [ProposalDecision("ab12cd34", "accept", 2), ProposalDecision("ab12cd34", "reject", None)]


def test_render_proposal_shows_the_es_version_when_there_is_one():
    t = make_topic()
    p = make_proposal(topic=t, script="Piada sobre a medida.")
    text = render_proposal(p, t, es="Chiste sobre la medida.")
    assert "Versão ES:\nChiste sobre la medida." in text
    assert text.index("Piada sobre a medida.") < text.index("Versão ES:") < text.index("Afirmações e fontes:")
    assert "Versão ES:" not in render_proposal(p, t) and "Versão ES:" not in render_proposal(p, t, es=None)


def test_render_proposal_cuts_the_es_version_to_about_400_letters():
    t = make_topic()
    text = render_proposal(make_proposal(topic=t), t, es="ñ" * 1000)
    assert "ñ" * 400 + "…" in text and "ñ" * 401 not in text


def test_send_proposal_includes_the_stored_es_translation_within_telegram_limit(tmp_path):
    store, topics, http, ch = setup(tmp_path)
    p = make_proposal(topic=topics[0], script="Piada. " * 300)
    store.save_proposals([p])
    store.save_translation(p.id, "es", "Chiste en español neutro.")
    ch.send_proposal(p, topics[0])
    sent = http.sent("sendMessage")[-1]["text"]
    assert len(sent) <= 4096 and "Versão ES:\nChiste en español neutro." in sent
    other = make_proposal("cd34ef56", topic=topics[0])
    store.save_proposals([other])
    ch.send_proposal(other, topics[0])
    assert "Versão ES:" not in http.sent("sendMessage")[-1]["text"]
