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


def test_tiktok_publisher_is_added_when_token_is_set(tmp_path):
    env = {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "1", "LLM_MODEL": "m", "ANTHROPIC_API_KEY": "k",
           "DB_PATH": str(tmp_path / "db.sqlite"), "TIKTOK_ACCESS_TOKEN": "x"}
    assert list(build_pipeline(env).publishers) == ["tiktok"]


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
    store.set_first_day(date(2026, 10, 10))
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
