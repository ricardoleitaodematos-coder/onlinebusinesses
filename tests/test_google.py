import base64
from types import SimpleNamespace

import pytest
from onlinebusinesses.providers.google import (GCSVideoHost, GoogleError, GoogleTTSVoice, ImagenVisuals,
                                               google_session_from_env)


class Resp:
    def __init__(self, status=200, body=None):
        self.status_code, self._body = status, body or {}

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def _do(self, method, url, **kw):
        self.calls.append((method, url, kw))
        r = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(r, Exception):
            raise r
        return r

    def post(self, url, **kw):
        return self._do("POST", url, **kw)

    def get(self, url, **kw):
        return self._do("GET", url, **kw)

    def put(self, url, **kw):
        return self._do("PUT", url, **kw)


def b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def test_tts_synthesizes_wav_with_configured_voice(tmp_path):
    s = FakeSession([Resp(body={"audioContent": b64(b"RIFFwav")})])
    out = GoogleTTSVoice(s, {"pt-PT": "pt-PT-Wavenet-F", "es": "es-ES-Neural2-F"}).synthesize("Olá", "pt-PT", tmp_path / "a.wav")
    assert out.read_bytes() == b"RIFFwav"
    method, url, kw = s.calls[0]
    assert (method, url) == ("POST", "https://texttospeech.googleapis.com/v1/text:synthesize")
    assert kw["json"] == {"input": {"text": "Olá"},
                          "voice": {"languageCode": "pt-PT", "name": "pt-PT-Wavenet-F"},
                          "audioConfig": {"audioEncoding": "LINEAR16"}}


def test_tts_spanish_language_code(tmp_path):
    s = FakeSession([Resp(body={"audioContent": b64(b"x")})])
    GoogleTTSVoice(s, {"pt-PT": "a", "es": "es-ES-Neural2-F"}).synthesize("Hola", "es", tmp_path / "a.wav")
    assert s.calls[0][2]["json"]["voice"] == {"languageCode": "es-ES", "name": "es-ES-Neural2-F"}


def test_tts_default_voices_from_env():
    v = GoogleTTSVoice.from_env(FakeSession([]), {"TTS_VOICE_ES": "es-ES-Neural2-A"})
    assert v.voices["es"] == "es-ES-Neural2-A" and v.voices["pt-PT"].startswith("pt-PT-")


def test_tts_unknown_language_and_http_error(tmp_path):
    v = GoogleTTSVoice(FakeSession([Resp(403)]), {"pt-PT": "p"})
    with pytest.raises(ValueError):
        v.synthesize("x", "fr", tmp_path / "a.wav")
    with pytest.raises(GoogleError) as e:
        v.synthesize("x", "pt-PT", tmp_path / "a.wav")
    assert "403" in str(e.value) and "https://" not in str(e.value)


def test_imagen_renders_one_png_per_prompt(tmp_path):
    s = FakeSession([Resp(body={"predictions": [{"bytesBase64Encoded": b64(b"png1")}]}),
                     Resp(body={"predictions": [{"bytesBase64Encoded": b64(b"png2")}]})])
    files = ImagenVisuals(s, "proj", "europe-west4", "imagen-x").render(["um gato", "um cão"], "cartoon", tmp_path / "f")
    assert [f.name for f in files] == ["frame-01.png", "frame-02.png"]
    assert files[1].read_bytes() == b"png2"
    method, url, kw = s.calls[0]
    assert url == ("https://europe-west4-aiplatform.googleapis.com/v1/projects/proj/locations/europe-west4"
                   "/publishers/google/models/imagen-x:predict")
    assert kw["json"]["parameters"]["aspectRatio"] == "9:16" and kw["json"]["parameters"]["sampleCount"] == 1
    prompt = kw["json"]["instances"][0]["prompt"]
    assert "um gato" in prompt and "cartoon" in prompt.lower() and "real people" in prompt.lower()


def test_imagen_errors_are_clean(tmp_path):
    v = ImagenVisuals(FakeSession([Resp(500)]), "proj", "us-central1", "m")
    with pytest.raises(GoogleError) as e:
        v.render(["x"], "abstract", tmp_path)
    assert "500" in str(e.value) and "proj" not in str(e.value)
    v = ImagenVisuals(FakeSession([Resp(body={"predictions": []})]), "proj", "us-central1", "m")
    with pytest.raises(GoogleError, match="sem imagem"):
        v.render(["x"], "abstract", tmp_path)


def test_gcs_upload_returns_public_url(tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"video")
    s = FakeSession([Resp(body={"name": "videos/abc-v.mp4"})])
    url = GCSVideoHost(s, "my-bucket").upload(video)
    method, call_url, kw = s.calls[0]
    assert method == "POST" and call_url.startswith("https://storage.googleapis.com/upload/storage/v1/b/my-bucket/o")
    assert kw["params"]["uploadType"] == "media" and kw["data"] == b"video"
    assert kw["headers"]["Content-Type"] == "video/mp4"
    assert url == f"https://storage.googleapis.com/my-bucket/{kw['params']['name']}"
    assert kw["params"]["name"].endswith("v.mp4")


def test_gcs_error_has_no_url(tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    with pytest.raises(GoogleError) as e:
        GCSVideoHost(FakeSession([Resp(401)]), "b").upload(video)
    assert "401" in str(e.value) and "http" not in str(e.value)


def test_network_exception_is_wrapped(tmp_path):
    v = GoogleTTSVoice(FakeSession([RuntimeError("https://x/?key=SECRET")]), {"pt-PT": "p"})
    with pytest.raises(GoogleError) as e:
        v.synthesize("x", "pt-PT", tmp_path / "a.wav")
    assert "SECRET" not in str(e.value)


def test_session_factory_uses_google_auth_default(monkeypatch):
    import sys
    import types
    seen = {}
    auth = types.ModuleType("google.auth")
    auth.default = lambda scopes=None: (object(), "p")
    transport = types.ModuleType("google.auth.transport")
    treq = types.ModuleType("google.auth.transport.requests")
    treq.AuthorizedSession = lambda creds: seen.setdefault("session", SimpleNamespace(creds=creds))
    google = types.ModuleType("google")
    google.auth = auth
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.auth", auth)
    monkeypatch.setitem(sys.modules, "google.auth.transport", transport)
    monkeypatch.setitem(sys.modules, "google.auth.transport.requests", treq)
    assert google_session_from_env({}) is seen["session"]
