import pytest
from builders import NOW
from fakes import FakeApi
from onlinebusinesses.models import Insights
from onlinebusinesses.publishers.base import PublishError
from onlinebusinesses.publishers.instagram import InstagramPublisher
from onlinebusinesses.publishers.tiktok import TikTokDraftPublisher

BASE = "https://graph.instagram.com"


class FakeHost:
    def __init__(self):
        self.uploaded = []

    def upload(self, path):
        self.uploaded.append(path)
        return "https://cdn.test/v.mp4"


@pytest.fixture
def video(tmp_path):
    f = tmp_path / "v.mp4"
    f.write_bytes(b"x" * 1000)
    return f


def ig(api, sleeps=None, **kw):
    sleeps = sleeps if sleeps is not None else []
    return InstagramPublisher(api, FakeHost(), "u1", "TOK", sleep=sleeps.append, poll_interval=1.0, **kw)


def ig_routes(statuses):
    return {"POST /u1/media_publish": {"id": "m1"}, "POST /u1/media": {"id": "c1"},
            "GET /c1": [{"status_code": s} for s in statuses]}


def test_instagram_creates_container_polls_then_publishes(video):
    api, sleeps = FakeApi(ig_routes(["IN_PROGRESS", "FINISHED"])), []
    out = ig(api, sleeps).publish(video, "legenda", True, "k1")
    assert out == "m1"
    assert [(m, u.removeprefix(BASE)) for m, u, *_ in api.calls] == [
        ("POST", "/u1/media"), ("GET", "/c1"), ("GET", "/c1"), ("POST", "/u1/media_publish")]
    create = api.calls[0][2]
    assert create == {"media_type": "REELS", "video_url": "https://cdn.test/v.mp4", "caption": "legenda",
                      "is_ai_generated": True, "access_token": "TOK"}
    assert api.calls[-1][2] == {"creation_id": "c1", "access_token": "TOK"}
    assert len(sleeps) == 1


def test_instagram_error_status_raises_and_never_publishes(video):
    api = FakeApi(ig_routes(["ERROR"]))
    with pytest.raises(PublishError):
        ig(api).publish(video, "c", True, "k")
    assert not any(u.endswith("media_publish") for _, u, *_ in api.calls)


def test_instagram_poll_timeout_raises(video):
    api = FakeApi(ig_routes(["IN_PROGRESS"]))
    with pytest.raises(PublishError, match="tempo"):
        ig(api, max_polls=3).publish(video, "c", True, "k")
    assert not any(u.endswith("media_publish") for _, u, *_ in api.calls)


def test_instagram_http_failure_becomes_publish_error(video):
    api = FakeApi({"POST /u1/media": OSError("rede em baixo")})
    with pytest.raises(PublishError):
        ig(api).publish(video, "c", True, "k")


def test_instagram_insights_maps_metrics():
    data = {"data": [{"name": n, "values": [{"value": v}]} for n, v in
                     [("views", 100), ("likes", 10), ("comments", 3), ("shares", 2), ("ig_reels_avg_watch_time", 4500)]]}
    api = FakeApi({"GET /m1/insights": data})
    assert ig(api).insights("m1") == Insights(100, 10, 3, 2, 4.5)
    assert "ig_reels_avg_watch_time" in api.calls[0][2]["metric"]


TT_INIT = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"


def tt_routes(put=201):
    return {"POST /inbox/video/init/": {"data": {"publish_id": "p1", "upload_url": "https://up.test/u"},
                                         "error": {"code": "ok"}}, "PUT /u": put}


def test_tiktok_uploads_draft_to_inbox_never_direct_post(video):
    api = FakeApi(tt_routes())
    assert TikTokDraftPublisher(api, "TTOK").publish(video, "legenda", True, "k") == "p1"
    method, url, body, headers = api.calls[0]
    assert (method, url) == ("POST", TT_INIT) and headers["Authorization"] == "Bearer TTOK"
    assert body == {"source_info": {"source": "FILE_UPLOAD", "video_size": 1000, "chunk_size": 1000,
                                    "total_chunk_count": 1}}
    put = api.calls[1]
    assert put[1] == "https://up.test/u" and put[3]["Content-Range"] == "bytes 0-999/1000"
    assert put[3]["Content-Type"] == "video/mp4" and put[2] == b"x" * 1000
    assert not any("post/publish/video/init" in u for _, u, *_ in api.calls)


def test_tiktok_upload_not_201_raises(video):
    with pytest.raises(PublishError):
        TikTokDraftPublisher(FakeApi(tt_routes(put=500)), "T").publish(video, "c", True, "k")


def test_tiktok_error_in_init_raises(video):
    api = FakeApi({"POST /inbox/video/init/": {"error": {"code": "spam_risk", "message": "x"}}})
    with pytest.raises(PublishError, match="spam_risk"):
        TikTokDraftPublisher(api, "T").publish(video, "c", True, "k")


def test_tiktok_rejects_video_over_64mb(tmp_path):
    big = tmp_path / "big.mp4"
    with open(big, "wb") as f:
        f.truncate(65 * 1024 * 1024)
    with pytest.raises(PublishError, match="64"):
        TikTokDraftPublisher(FakeApi({}), "T").publish(big, "c", True, "k")


def test_tiktok_insights_not_available_for_drafts():
    with pytest.raises(NotImplementedError):
        TikTokDraftPublisher(FakeApi({}), "T").insights("p1")
