import httpx
import pytest
from onlinebusinesses.brief import TelegramChannel
from onlinebusinesses.http import HttpError, HttpxClient
from onlinebusinesses.store import Store


def test_post_and_get_json_roundtrip():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"echo": request.read().decode()})
        return httpx.Response(200, json={"q": request.url.params.get("a")})

    c = HttpxClient(transport=httpx.MockTransport(handler))
    assert c.get_json("https://x.test/g", {"a": "1"}) == {"q": "1"}
    assert '"k"' in c.post_json("https://x.test/p", {"k": 1})["echo"]


def test_http_error_raises_without_url_path_or_query():
    c = HttpxClient(transport=httpx.MockTransport(lambda r: httpx.Response(500, json={})))
    with pytest.raises(HttpError) as info:
        c.get_json("https://x.test/g/SEGREDO", {"access_token": "TOKQ"})
    e = info.value
    assert (e.status, e.method, e.host) == (500, "GET", "x.test")
    assert "SEGREDO" not in str(e) and "TOKQ" not in str(e) and "TOKQ" not in repr(e)


def test_network_error_keeps_only_the_host():
    def handler(request):
        raise httpx.ConnectError(f"ligação recusada a {request.url}", request=request)

    c = HttpxClient(transport=httpx.MockTransport(handler))
    for call in (lambda: c.post_json("https://x.test/botSEGREDO/sendMessage", {}),
                 lambda: c.put_bytes("https://x.test/up?token=SEGREDO", b"x", {})):
        with pytest.raises(HttpError) as info:
            call()
        assert info.value.host == "x.test" and "SEGREDO" not in str(info.value)


def test_telegram_400_does_not_leak_the_bot_token(tmp_path):
    store = Store(tmp_path / "t.sqlite")
    store.init()
    http = HttpxClient(transport=httpx.MockTransport(lambda r: httpx.Response(400, json={"ok": False})))
    ch = TelegramChannel(http, "123456:SEGREDO-DO-BOT", 1, store)
    with pytest.raises(HttpError) as info:
        ch.notify("olá")
    assert "SEGREDO-DO-BOT" not in str(info.value) and "SEGREDO-DO-BOT" not in repr(info.value)


def test_headers_and_put_bytes():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen[request.method] = (request.headers.get("authorization"), request.headers.get("content-range"),
                                request.read())
        return httpx.Response(201 if request.method == "PUT" else 200, json={})

    c = HttpxClient(transport=httpx.MockTransport(handler))
    c.post_json("https://x.test/p", {}, headers={"Authorization": "Bearer t"})
    status = c.put_bytes("https://x.test/u", b"abc", {"Content-Range": "bytes 0-2/3"})
    assert seen["POST"][0] == "Bearer t"
    assert status == 201 and seen["PUT"][1:] == ("bytes 0-2/3", b"abc")
