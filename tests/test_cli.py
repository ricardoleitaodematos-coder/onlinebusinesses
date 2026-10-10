from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from onlinebusinesses.cli import ConfigError, build_pipeline, main
from onlinebusinesses.pipeline import Pipeline
from onlinebusinesses.unconfigured import NullSearch, UnconfiguredVisuals, UnconfiguredVoice

NOW = datetime(2026, 10, 10, 8, 0, tzinfo=timezone.utc)


class Recorder:
    def __init__(self):
        self.calls = []

    def stage_research(self, now):
        self.calls.append(("research", now))
        return []

    def stage_poll(self, now):
        self.calls.append(("poll", now))

    def stage_publish(self, now):
        self.calls.append(("publish", now))
        return {}


@pytest.mark.parametrize("command", ["research", "poll", "publish"])
def test_commands_dispatch_to_stages(command):
    rec = Recorder()
    assert main([command], {}, factory=lambda env: rec, now=lambda: NOW) == 0
    assert rec.calls == [(command, NOW)]


def test_unknown_command_exits_with_usage_error(capsys):
    assert main(["voar"], {}, factory=lambda env: Recorder(), now=lambda: NOW) == 2
    assert "research" in capsys.readouterr().err


def test_config_error_is_reported_not_raised(capsys):
    def factory(env):
        raise ConfigError("falta TELEGRAM_BOT_TOKEN")

    assert main(["poll"], {}, factory=factory, now=lambda: NOW) == 1
    assert "TELEGRAM_BOT_TOKEN" in capsys.readouterr().err


def test_build_pipeline_requires_telegram():
    with pytest.raises(ConfigError, match="TELEGRAM_BOT_TOKEN"):
        build_pipeline({"LLM_MODEL": "m", "ANTHROPIC_API_KEY": "k"})


def test_build_pipeline_with_minimal_env(tmp_path):
    env = {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "1", "LLM_MODEL": "m", "ANTHROPIC_API_KEY": "k",
           "DB_PATH": str(tmp_path / "db.sqlite"), "OUT_DIR": str(tmp_path / "out")}
    pipe = build_pipeline(env)
    assert isinstance(pipe, Pipeline) and pipe.publishers == {}
    assert isinstance(pipe.search, NullSearch)
    assert pipe.aliases["bbc.com"] == "bbc.co.uk"


def test_tiktok_publisher_is_added_when_token_is_set(tmp_path):
    env = {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "1", "LLM_MODEL": "m", "ANTHROPIC_API_KEY": "k",
           "DB_PATH": str(tmp_path / "db.sqlite"), "TIKTOK_ACCESS_TOKEN": "x"}
    assert list(build_pipeline(env).publishers) == ["tiktok"]


def test_es_tiktok_publisher_is_registered_per_language(tmp_path):
    env = {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "1", "LLM_MODEL": "m", "ANTHROPIC_API_KEY": "k",
           "DB_PATH": str(tmp_path / "db.sqlite"), "TIKTOK_ACCESS_TOKEN_ES": "x"}
    assert list(build_pipeline(env).publishers) == ["tiktok:es"]
    both = build_pipeline({**env, "TIKTOK_ACCESS_TOKEN": "y"})
    assert list(both.publishers) == ["tiktok", "tiktok:es"] and both.settings.publish_languages == ("pt-PT", "es")


def test_es_tiktok_token_is_redacted(tmp_path, capsys):
    class Boom(Recorder):
        def stage_poll(self, now):
            raise RuntimeError("falhou com TT-ES-SEGREDO")

    env = {"TIKTOK_ACCESS_TOKEN_ES": "TT-ES-SEGREDO", "OUT_DIR": str(tmp_path)}
    assert main(["poll"], env, factory=lambda e: Boom(), now=lambda: NOW) == 1
    err = capsys.readouterr().err
    assert "TT-ES-SEGREDO" not in err and "***" in err


def test_unconfigured_providers_fail_with_a_pointer_to_the_setup_doc(tmp_path):
    assert NullSearch().search("x", NOW) == []
    with pytest.raises(RuntimeError, match="setup-ricardo"):
        UnconfiguredVoice().synthesize("t", "pt-PT", tmp_path / "a.wav")
    with pytest.raises(RuntimeError, match="setup-ricardo"):
        UnconfiguredVisuals().render(["x"], "cartoon", tmp_path)


def report_pipeline(tmp_path):
    from datetime import date

    from onlinebusinesses.config import load_settings
    from onlinebusinesses.store import Store

    store = Store(tmp_path / "t.sqlite")
    store.init()
    store.set_first_day(date(2026, 9, 1))  # a pesquisa começou antes; conta a 1.ª publicação
    store.record_publication("p0", "instagram", "ig-0", date(2026, 10, 10))
    return SimpleNamespace(store=store, publishers={}, settings=load_settings({}))


def test_report_defaults_to_the_first_week_without_mandatory_approvals(tmp_path, capsys):
    pipe = report_pipeline(tmp_path)
    assert main(["report"], {}, factory=lambda env: pipe, now=lambda: NOW) == 0
    out = capsys.readouterr().out
    assert "Semana de 2026-10-17 a 2026-10-23" in out and "Sucesso: não" in out


def test_report_accepts_an_explicit_start_date(tmp_path, capsys):
    pipe = report_pipeline(tmp_path)
    assert main(["report", "2026-11-01"], {}, factory=lambda env: pipe, now=lambda: NOW) == 0
    assert "Semana de 2026-11-01 a 2026-11-07" in capsys.readouterr().out


def test_report_rejects_a_bad_date(tmp_path, capsys):
    pipe = report_pipeline(tmp_path)
    assert main(["report", "ontem"], {}, factory=lambda env: pipe, now=lambda: NOW) == 2


def test_unexpected_error_is_reported_with_tokens_redacted(tmp_path, capsys):
    class Boom(Recorder):
        def stage_poll(self, now):
            raise RuntimeError("POST https://api.telegram.org/botTG-SEGREDO/sendMessage falhou (chave AK-SEGREDO)")

    env = {"TELEGRAM_BOT_TOKEN": "TG-SEGREDO", "ANTHROPIC_API_KEY": "AK-SEGREDO", "OUT_DIR": str(tmp_path)}
    assert main(["poll"], env, factory=lambda e: Boom(), now=lambda: NOW) == 1
    err = capsys.readouterr().err
    assert "TG-SEGREDO" not in err and "AK-SEGREDO" not in err and "***" in err


def test_second_instance_does_nothing_while_the_command_lock_is_held(tmp_path):
    import fcntl

    rec, env = Recorder(), {"OUT_DIR": str(tmp_path)}
    with open(tmp_path / ".publish.lock", "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert main(["publish"], env, factory=lambda e: rec, now=lambda: NOW) == 0
        assert rec.calls == []
        assert main(["poll"], env, factory=lambda e: rec, now=lambda: NOW) == 0  # o lock é por comando
        assert rec.calls == [("poll", NOW)]
    assert main(["publish"], env, factory=lambda e: rec, now=lambda: NOW) == 0
    assert rec.calls[-1] == ("publish", NOW)


BASE = {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "1", "LLM_MODEL": "m", "ANTHROPIC_API_KEY": "k"}


def google_env(tmp_path, **extra):
    return {**BASE, "DB_PATH": str(tmp_path / "db.sqlite"), "GOOGLE_CLOUD_PROJECT": "proj", "GCS_BUCKET": "bkt", **extra}


def test_google_providers_are_wired_when_project_is_set(tmp_path):
    from onlinebusinesses.providers.google import GoogleTTSVoice, ImagenVisuals

    made = []
    pipe = build_pipeline(google_env(tmp_path, VERTEX_LOCATION="europe-west4", IMAGEN_MODEL="img-m"),
                          session_factory=lambda env: made.append(1) or "SESSION")
    assert isinstance(pipe.voice, GoogleTTSVoice) and isinstance(pipe.visuals, ImagenVisuals)
    assert (pipe.visuals.project, pipe.visuals.location, pipe.visuals.model) == ("proj", "europe-west4", "img-m")
    assert made == [1]  # uma só sessão partilhada


def test_without_google_project_stays_unconfigured(tmp_path):
    pipe = build_pipeline({**BASE, "DB_PATH": str(tmp_path / "db.sqlite")},
                          session_factory=lambda env: pytest.fail("não devia criar sessão Google"))
    assert isinstance(pipe.voice, UnconfiguredVoice) and isinstance(pipe.visuals, UnconfiguredVisuals)


def test_brave_search_is_wired_when_key_is_set(tmp_path):
    from onlinebusinesses.providers.brave import BraveSearch

    pipe = build_pipeline({**BASE, "DB_PATH": str(tmp_path / "db.sqlite"), "BRAVE_API_KEY": "bk"})
    assert isinstance(pipe.search, BraveSearch)


def test_instagram_publishers_need_bucket_and_credentials(tmp_path):
    from onlinebusinesses.providers.google import GCSVideoHost

    env = google_env(tmp_path, INSTAGRAM_USER_ID="1", INSTAGRAM_ACCESS_TOKEN="a",
                     INSTAGRAM_USER_ID_ES="2", INSTAGRAM_ACCESS_TOKEN_ES="b")
    pipe = build_pipeline(env, session_factory=lambda e: "S")
    assert list(pipe.publishers) == ["instagram", "instagram:es"]
    assert isinstance(pipe.publishers["instagram"].host, GCSVideoHost) and pipe.publishers["instagram:es"].user_id == "2"
    no_bucket = {k: v for k, v in env.items() if k != "GCS_BUCKET"}
    assert list(build_pipeline(no_bucket, session_factory=lambda e: "S").publishers) == []
    only_pt = {k: v for k, v in env.items() if not k.endswith("_ES")}
    assert list(build_pipeline(only_pt, session_factory=lambda e: "S").publishers) == ["instagram"]


def test_new_secrets_are_redacted():
    from onlinebusinesses.cli import redact

    env = {"BRAVE_API_KEY": "BR-S", "INSTAGRAM_ACCESS_TOKEN_ES": "IG-ES-S"}
    assert redact("a BR-S b IG-ES-S", env) == "a *** b ***"


def test_env_file_fills_missing_variables_only(tmp_path):
    from onlinebusinesses.cli import load_env_file

    f = tmp_path / "e.env"
    f.write_text("# c\nA=1\nB='dois' \nexport C=\"três\"\n\nlinha inválida\nD=x=y\n")
    merged = load_env_file({"A": "real", "ENV_FILE": str(f)})
    assert merged["A"] == "real" and merged["B"] == "dois" and merged["C"] == "três" and merged["D"] == "x=y"
    assert load_env_file({"ENV_FILE": str(tmp_path / "nao-existe")}) == {"ENV_FILE": str(tmp_path / "nao-existe")}
