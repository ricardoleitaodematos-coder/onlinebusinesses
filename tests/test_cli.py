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
