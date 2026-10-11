import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy" / "instalar-na-google-cloud.sh"
# Afinações que o Ricardo não precisa de definir (valores por omissão do código).
TUNING = {"FEEDS_PATH", "SOURCES_PATH", "PICKS_PER_DAY", "TOPICS_PER_DAY", "REQUIRE_ACCEPT_DAYS", "REVISION_LIMIT",
          "PUBLISH_HOLD_MINUTES", "TZ_NAME", "ENV_FILE"}


def env_vars_read_by_the_code() -> set[str]:
    names: set[str] = set()
    for f in (ROOT / "src" / "onlinebusinesses").rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        names |= set(re.findall(r'env(?:\.get)?[\(\[]\s*"([A-Z][A-Z0-9_]+)"', text))
    names |= {"INSTAGRAM_USER_ID", "INSTAGRAM_ACCESS_TOKEN", "INSTAGRAM_USER_ID_ES", "INSTAGRAM_ACCESS_TOKEN_ES"}
    return names - TUNING


def test_script_mentions_every_variable_the_cli_reads():
    text = SCRIPT.read_text(encoding="utf-8")
    missing = sorted(n for n in env_vars_read_by_the_code() if n not in text)
    assert not missing, f"o script não menciona: {missing}"


def test_script_is_strict_and_executable():
    text = SCRIPT.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env bash") and "set -euo pipefail" in text
    assert SCRIPT.stat().st_mode & 0o111


def test_script_syntax_is_valid():
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck não instalado")
def test_shellcheck_passes():
    subprocess.run(["shellcheck", str(SCRIPT)], check=True)


SECRETS = ("TELEGRAM_BOT_TOKEN", "ANTHROPIC_API_KEY", "BRAVE_API_KEY", "INSTAGRAM_ACCESS_TOKEN",
           "INSTAGRAM_ACCESS_TOKEN_ES", "TIKTOK_ACCESS_TOKEN", "TIKTOK_ACCESS_TOKEN_ES", "GCP_SA_KEY")


def script_lines() -> list[str]:
    return [ln for ln in SCRIPT.read_text(encoding="utf-8").splitlines() if not ln.lstrip().startswith("#")]


def test_script_has_no_ssh_scp_or_interactive_reads():
    code = "\n".join(script_lines())
    assert not re.search(r"\b(ssh|scp)\b", code), "a sessão cloud não tem SSH"
    assert not re.search(r"\bread\b", code), "o script não pode ser interativo"


def test_script_never_prints_secret_variables():
    assert "set -x" not in "\n".join(script_lines())
    for ln in script_lines():
        if re.search(r"\b(echo|printf)\b", ln) and not re.search(r">>?\s*\"?\$", ln):
            for name in SECRETS:
                assert f"${name}" not in ln and f"${{{name}" not in ln, f"ecoa um segredo: {ln.strip()}"
    # chaves do ficheiro de segredos só vão para ficheiro, nunca para o stdout
    assert "${!name}" not in "\n".join(ln for ln in script_lines() if "printf" in ln and ">>" not in ln)


def test_script_uses_service_account_key_secret_manager_and_private_deploy_bucket():
    text = SCRIPT.read_text(encoding="utf-8")
    for needle in ("GCP_SA_KEY", "activate-service-account", "umask 077", "trap ", "git", "archive HEAD",
                   "onlinebusinesses-env", "secretmanager.googleapis.com", "secretAccessor",
                   "-onlinebusinesses-deploy", "app.tar.gz", "startup-script", "instances reset"):
        assert needle in text, needle


def test_script_fails_clearly_without_required_secrets(tmp_path):
    env = {"PATH": "/usr/bin:/bin", "GCP_SA_KEY": "{}"}
    r = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=30)
    assert r.returncode != 0
    assert "TELEGRAM_BOT_TOKEN" in r.stderr and "TELEGRAM_CHAT_ID" in r.stderr and "ANTHROPIC_API_KEY" in r.stderr
