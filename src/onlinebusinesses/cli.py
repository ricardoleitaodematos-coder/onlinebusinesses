from __future__ import annotations

import fcntl
import sys
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterator, Mapping, Sequence

import httpx

from .brief import TelegramChannel
from .config import load_aliases, load_settings, load_sources, today_lisbon
from .gates import load_blocklist
from .http import HttpxClient
from .llm import build_llm
from .metrics import collect_insights, weekly_report
from .pipeline import Pipeline
from .providers.brave import BraveSearch
from .providers.google import GCSVideoHost, GoogleTTSVoice, ImagenVisuals, google_session_from_env
from .publishers.instagram import InstagramPublisher
from .publishers.tiktok import TikTokDraftPublisher
from .store import Store
from .unconfigured import NullSearch, UnconfiguredVisuals, UnconfiguredVoice

COMMANDS = ("research", "poll", "publish", "report")
SECRET_VARS = ("TELEGRAM_BOT_TOKEN", "ANTHROPIC_API_KEY", "TIKTOK_ACCESS_TOKEN", "TIKTOK_ACCESS_TOKEN_ES",
               "INSTAGRAM_ACCESS_TOKEN", "INSTAGRAM_ACCESS_TOKEN_ES", "BRAVE_API_KEY")
DEFAULT_ENV_FILE = "/etc/onlinebusinesses.env"
DEFAULT_VERTEX_LOCATION = "us-central1"  # regiões europeias do Imagen por confirmar (docs/compliance.md)
DEFAULT_IMAGEN_MODEL = "imagen-4.0-generate-001"  # descontinuação anunciada a 2026-06-30: ver docs/compliance.md


class ConfigError(Exception):
    pass


def _get_text(url: str) -> str:
    response = httpx.get(url, timeout=30, follow_redirects=True, headers={"User-Agent": "onlinebusinesses/0.0.1"})
    response.raise_for_status()
    return response.text


def load_env_file(env: Mapping[str, str]) -> dict[str, str]:
    """Junta o ficheiro `.env` (ENV_FILE, por omissão /etc/onlinebusinesses.env) às variáveis; o ambiente real ganha."""
    merged = dict(env)
    path = Path(env.get("ENV_FILE", DEFAULT_ENV_FILE))
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return merged
    for line in lines:
        line = line.strip().removeprefix("export ").strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name, value = name.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        merged.setdefault(name, value)
    return merged


def build_pipeline(env: Mapping[str, str],
                   session_factory: Callable[[Mapping[str, str]], object] = google_session_from_env) -> Pipeline:
    settings = load_settings(env)
    token = env.get("TELEGRAM_BOT_TOKEN")
    if not token or settings.telegram_chat_id is None:
        raise ConfigError("faltam TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID (ver docs/setup-ricardo.md)")
    try:
        llm = build_llm(env)
    except ValueError as e:
        raise ConfigError(str(e)) from e
    store = Store(settings.db_path)
    store.init()
    http = HttpxClient()
    publishers = {}
    if env.get("TIKTOK_ACCESS_TOKEN"):
        publishers["tiktok"] = TikTokDraftPublisher(http, env["TIKTOK_ACCESS_TOKEN"])
    if env.get("TIKTOK_ACCESS_TOKEN_ES"):  # conta TikTok em espanhol: publica a versão ES
        publishers["tiktok:es"] = TikTokDraftPublisher(http, env["TIKTOK_ACCESS_TOKEN_ES"])
    search = BraveSearch(http, env["BRAVE_API_KEY"]) if env.get("BRAVE_API_KEY") else NullSearch()
    voice, visuals = UnconfiguredVoice(), UnconfiguredVisuals()
    project, bucket = env.get("GOOGLE_CLOUD_PROJECT"), env.get("GCS_BUCKET")
    if project or bucket:
        session = session_factory(env)  # uma só sessão autenticada para TTS, Imagen e Cloud Storage
        if project:
            voice = GoogleTTSVoice.from_env(session, env)  # type: ignore[arg-type]
            visuals = ImagenVisuals(session, project, env.get("VERTEX_LOCATION") or DEFAULT_VERTEX_LOCATION,  # type: ignore[arg-type]
                                    env.get("IMAGEN_MODEL") or DEFAULT_IMAGEN_MODEL)
        if bucket:  # o Instagram exige um URL público: só com alojamento no Cloud Storage
            host = GCSVideoHost(session, bucket)  # type: ignore[arg-type]
            for key, suffix in (("instagram", ""), ("instagram:es", "_ES")):
                if env.get(f"INSTAGRAM_USER_ID{suffix}") and env.get(f"INSTAGRAM_ACCESS_TOKEN{suffix}"):
                    publishers[key] = InstagramPublisher(http, host, env[f"INSTAGRAM_USER_ID{suffix}"],
                                                         env[f"INSTAGRAM_ACCESS_TOKEN{suffix}"])
    return Pipeline(store, TelegramChannel(http, token, settings.telegram_chat_id, store, settings.picks_per_day),
                    llm, search, voice, visuals, publishers, settings, _get_text,
                    load_blocklist(Path("config/blocklist.toml")), load_sources(settings.sources_path),
                    settings.out_dir / "work", aliases=load_aliases(settings.sources_path))


def redact(text: str, env: Mapping[str, str]) -> str:
    for name in SECRET_VARS:
        if value := env.get(name):
            text = text.replace(value, "***")
    return text


@contextmanager
def command_lock(out_dir: Path, command: str) -> Iterator[bool]:
    """Lock por comando (out_dir/.<comando>.lock): um cron sobreposto não corre o mesmo comando duas vezes."""
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / f".{command}.lock", "w") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True


def main(argv: Sequence[str], env: Mapping[str, str], factory: Callable[[Mapping[str, str]], Pipeline] = build_pipeline,
         now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> int:
    usage = f"uso: python -m onlinebusinesses {{{'|'.join(COMMANDS)}}} (report aceita uma data AAAA-MM-DD)"
    if not argv or argv[0] not in COMMANDS or len(argv) > (2 if argv[0] == "report" else 1):
        print(usage, file=sys.stderr)
        return 2
    try:
        report_start = date.fromisoformat(argv[1]) if len(argv) == 2 else None
    except ValueError:
        print(usage, file=sys.stderr)
        return 2
    try:
        with command_lock(load_settings(env).out_dir, argv[0]) as acquired:
            if not acquired:
                return 0  # outra execução do mesmo comando ainda está a correr
            return _run(argv[0], report_start, env, factory, now)
    except ConfigError as e:
        print(redact(f"configuração em falta: {e}", env), file=sys.stderr)
        return 1
    except Exception as e:  # nunca deixar sair um traceback com URLs ou tokens
        print(redact(f"erro em {argv[0]}: {type(e).__name__}: {e}", env), file=sys.stderr)
        return 1


def _run(command: str, report_start: date | None, env: Mapping[str, str],
         factory: Callable[[Mapping[str, str]], Pipeline], now: Callable[[], datetime]) -> int:
    pipeline = factory(env)
    if command == "report":
        collect_insights(pipeline.store, pipeline.publishers)
        first = pipeline.store.first_publication_day()
        start = report_start or (first + timedelta(days=pipeline.settings.require_accept_days) if first
                                 else today_lisbon(now()))
        print(weekly_report(pipeline.store, start))
        return 0
    stage = {"research": pipeline.stage_research, "poll": pipeline.stage_poll, "publish": pipeline.stage_publish}
    stage[command](now())
    return 0
