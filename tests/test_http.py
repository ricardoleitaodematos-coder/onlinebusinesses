import httpx
import pytest
from onlinebusinesses.http import HttpxClient


def test_post_and_get_json_roundtrip():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"echo": request.read().decode()})
        return httpx.Response(200, json={"q": request.url.params.get("a")})

    c = HttpxClient(transport=httpx.MockTransport(handler))
    assert c.get_json("https://x.test/g", {"a": "1"}) == {"q": "1"}
    assert '"k"' in c.post_json("https://x.test/p", {"k": 1})["echo"]


def test_http_error_raises():
    c = HttpxClient(transport=httpx.MockTransport(lambda r: httpx.Response(500, json={})))
    with pytest.raises(httpx.HTTPStatusError):
        c.get_json("https://x.test/g")
