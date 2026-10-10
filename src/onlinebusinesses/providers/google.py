"""Fornecedores Google Cloud (uma só conta): voz, imagens e alojamento do vídeo.

Documentação oficial consultada a 2026-10-10 (ver docs/compliance.md, secção Google Cloud):
- TTS: POST https://texttospeech.googleapis.com/v1/text:synthesize; resposta `audioContent` em base64
  (LINEAR16 inclui cabeçalho WAV). Vozes: https://docs.cloud.google.com/text-to-speech/docs/list-voices-and-types
- Imagen: POST https://REGION-aiplatform.googleapis.com/v1/projects/P/locations/REGION/publishers/google/models/M:predict
  https://docs.cloud.google.com/vertex-ai/generative-ai/docs/image/generate-images
- Cloud Storage: upload simples (JSON API, uploadType=media) e URL público https://storage.googleapis.com/BUCKET/OBJETO.
`session` imita google.auth.transport.requests.AuthorizedSession (post/get/put) e é injetável nos testes.
"""
from __future__ import annotations

import base64
import hashlib
import mimetypes
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

DEFAULT_VOICES = {"pt-PT": "pt-PT-Wavenet-F", "es": "es-ES-Neural2-F"}
_LANG_CODES = {"pt-PT": "pt-PT", "es": "es-ES"}
TTS_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"
GCS_UPLOAD = "https://storage.googleapis.com/upload/storage/v1/b/{bucket}/o"
SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]
_STYLES = {"cartoon": "cartoon illustration", "illustration": "flat editorial illustration",
           "abstract": "abstract art"}
_NO_PEOPLE = ("No photorealistic depictions of real people, no real faces or celebrities, no text or logos; "
              "vertical 9:16 composition.")


class GoogleError(Exception):
    """Erro de um serviço Google sem URL nem tokens: só serviço, estado e método."""

    def __init__(self, service: str, method: str, status: int | None, detail: str = ""):
        self.service, self.method, self.status = service, method, status
        base = f"HTTP {status} em {method} {service}" if status is not None else f"falha em {method} {service}"
        super().__init__(f"{base}: {detail}" if detail else base)


class Session(Protocol):
    def post(self, url: str, **kwargs: Any) -> Any: ...

    def get(self, url: str, **kwargs: Any) -> Any: ...

    def put(self, url: str, **kwargs: Any) -> Any: ...


def _call(session: Session, service: str, method: str, url: str, **kwargs: Any) -> dict:
    try:
        r = getattr(session, method.lower())(url, timeout=120, **kwargs)
    except Exception as e:  # a mensagem original pode levar URLs ou chaves
        raise GoogleError(service, method, None, type(e).__name__) from None
    if r.status_code >= 400:
        raise GoogleError(service, method, r.status_code)
    try:
        return r.json()
    except Exception:
        raise GoogleError(service, method, r.status_code, "resposta inválida") from None


class GoogleTTSVoice:
    def __init__(self, session: Session, voices: Mapping[str, str]):
        self.session, self.voices = session, dict(voices)

    @classmethod
    def from_env(cls, session: Session, env: Mapping[str, str]) -> "GoogleTTSVoice":
        return cls(session, {"pt-PT": env.get("TTS_VOICE_PT") or DEFAULT_VOICES["pt-PT"],
                             "es": env.get("TTS_VOICE_ES") or DEFAULT_VOICES["es"]})

    def synthesize(self, text: str, lang: str, out: Path) -> Path:
        if lang not in self.voices:
            raise ValueError(f"língua sem voz configurada: {lang}")
        data = _call(self.session, "texttospeech", "POST", TTS_URL, json={
            "input": {"text": text},
            "voice": {"languageCode": _LANG_CODES.get(lang, lang), "name": self.voices[lang]},
            "audioConfig": {"audioEncoding": "LINEAR16"}})
        if not data.get("audioContent"):
            raise GoogleError("texttospeech", "POST", None, "sem áudio")
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(base64.b64decode(data["audioContent"]))
        return out


class ImagenVisuals:
    def __init__(self, session: Session, project: str, location: str, model: str):
        self.session, self.project, self.location, self.model = session, project, location, model

    def render(self, prompts: Sequence[str], style: str, out_dir: Path) -> list[Path]:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        host = "aiplatform.googleapis.com" if self.location == "global" else f"{self.location}-aiplatform.googleapis.com"
        url = (f"https://{host}/v1/projects/{self.project}/locations/{self.location}"
               f"/publishers/google/models/{self.model}:predict")
        files = []
        for i, prompt in enumerate(prompts, 1):
            full = f"{prompt}. Style: {_STYLES.get(style, style)}. {_NO_PEOPLE}"
            data = _call(self.session, "aiplatform", "POST", url, json={
                "instances": [{"prompt": full}],
                "parameters": {"sampleCount": 1, "aspectRatio": "9:16", "personGeneration": "dont_allow"}})
            preds = data.get("predictions") or []
            if not preds or not preds[0].get("bytesBase64Encoded"):
                raise GoogleError("aiplatform", "POST", None, "sem imagem na resposta (filtro de segurança?)")
            path = out_dir / f"frame-{i:02d}.png"
            path.write_bytes(base64.b64decode(preds[0]["bytesBase64Encoded"]))
            files.append(path)
        return files


class GCSVideoHost:
    def __init__(self, session: Session, bucket: str):
        self.session, self.bucket = session, bucket

    def upload(self, path: Path) -> str:
        path = Path(path)
        data = path.read_bytes()
        name = f"videos/{hashlib.sha256(data).hexdigest()[:12]}-{path.name}"
        _call(self.session, "storage", "POST", GCS_UPLOAD.format(bucket=self.bucket),
              params={"uploadType": "media", "name": name}, data=data,
              headers={"Content-Type": mimetypes.guess_type(path.name)[0] or "application/octet-stream"})
        return f"https://storage.googleapis.com/{self.bucket}/{name}"


def google_session_from_env(env: Mapping[str, str]) -> Session:
    """Credenciais da VM (conta de serviço) ou GOOGLE_APPLICATION_CREDENTIALS, via google.auth.default()."""
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    credentials, _ = google.auth.default(scopes=SCOPES)
    return AuthorizedSession(credentials)
