"""FR #253: airc console service â€” offline acceptance."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from airc_console import (  # noqa: E402
    AircConsoleCore,
    AuthPolicy,
    ConsoleSessionManager,
    load_operators,
    machine_id,
    shop_channel,
)


def test_channel_naming_machinename():
    assert machine_id("IONOS") == "ionos"
    assert shop_channel("IONOS") == "#ionos"
    assert shop_channel("ce-priority-dev1") == "#ce-priority-dev1"


def test_auth_operators_only():
    auth = AuthPolicy(operators={"Simon", "bob-ionos"})
    assert auth.allow("simon")
    assert auth.allow("BOB-IONOS")
    assert not auth.allow("stranger")


def test_auth_account_required():
    auth = AuthPolicy(operators={"simon"}, accounts={"simonbarnett"}, require_account=True)
    assert not auth.allow("simon", account=None)
    assert not auth.allow("simon", account="*")
    assert auth.allow("simon", account="simonbarnett")
    assert not auth.allow("simon", account="other")


def test_refuse_empty_operators_loader(tmp_path: Path):
    assert load_operators(tmp_path / "missing.txt") == set()
    f = tmp_path / "ops.txt"
    f.write_text("# comment\nSimon\n\n", encoding="utf-8")
    assert load_operators(f) == {"Simon"}


def test_silent_on_channel_no_reply():
    auth = AuthPolicy(operators={"simon"})
    core = AircConsoleCore(machine="ionos", auth=auth)
    assert core.channel == "#ionos"
    assert core.may_speak_on_channel() is False
    r = core.handle_raw(":simon!s@h PRIVMSG #ionos :hello channel")
    assert r is not None
    assert r.action == "silent_channel"
    assert r.reply is None


def test_unauth_privmsg_denied():
    auth = AuthPolicy(operators={"simon"})
    core = AircConsoleCore(machine="ionos", auth=auth)
    r = core.handle_raw(":evil!e@h PRIVMSG console :whoami")
    assert r is not None
    assert r.action == "deny"
    assert "denied" in (r.reply or "")


def test_auth_privmsg_pipes_and_quit():
    auth = AuthPolicy(operators={"simon"})
    mgr = ConsoleSessionManager(shell=None, on_output=None, idle_sec=60)
    core = AircConsoleCore(machine="ionos", auth=auth, sessions=mgr)
    try:
        r = core.handle_raw(":simon!s@h PRIVMSG console :echo airc-fr253")
        assert r is not None
        assert r.action == "pipe"
        assert "simon" in mgr.active()
        r2 = core.handle_raw(":simon!s@h PRIVMSG console :.quit")
        assert r2 is not None
        assert r2.action == "close"
        time.sleep(0.2)
        assert "simon" not in mgr.active()
    finally:
        mgr.close_all()


def test_account_tag_line_auth():
    auth = AuthPolicy(operators={"simon"}, accounts={"simonbarnett"}, require_account=True)
    core = AircConsoleCore(machine="ionos", auth=auth)
    # tagged line without matching account map yet â€” account from tags used in allow()
    line = "@account=simonbarnett :simon!s@h PRIVMSG console :.help"
    r = core.handle_raw(line)
    assert r is not None
    assert r.action == "help"


def test_docs_and_install_scripts_exist():
    assert (ROOT / "docs" / "airc-console-fr253.md").is_file()
    assert (ROOT / "scripts" / "Install-AircConsole.ps1").is_file()
    assert (ROOT / "scripts" / "Install-AircConsole.cmd").is_file()
    assert (ROOT / "scripts" / "Start-AircConsole.ps1").is_file()
    assert (ROOT / "scripts" / "Start-AircConsole.cmd").is_file()
    assert (ROOT / "scripts" / "Pack-AircConsoleRelease.ps1").is_file()
    assert (ROOT / "src" / "airc_console" / "VERSION").is_file()
    skill = (ROOT / ".grok" / "skills" / "airc-console" / "SKILL.md").read_text(encoding="utf-8")
    assert "FR #253" in skill
    assert "silent" in skill.lower()


def test_fr256_cmd_wrappers_bypass_execution_policy():
    """Downloaded .ps1 fails AllSigned/Restricted; .cmd must Bypass + Unblock-File."""
    for name in ("Install-AircConsole.cmd", "Start-AircConsole.cmd"):
        text = (ROOT / "scripts" / name).read_text(encoding="utf-8", errors="replace")
        assert "ExecutionPolicy Bypass" in text, name
        assert "Unblock-File" in text, name
        assert ".ps1" in text, name
    pack = (ROOT / "scripts" / "Pack-AircConsoleRelease.ps1").read_text(encoding="utf-8")
    assert "Install-AircConsole.cmd" in pack
    assert "Start-AircConsole.cmd" in pack
    readme = (ROOT / "src" / "airc_console" / "README.md").read_text(encoding="utf-8")
    assert "not digitally signed" in readme.lower() or "FR #256" in readme
    assert "Install-AircConsole.cmd" in readme


def test_fr259_start_ps1_no_psscriptroot_in_param_defaults():
    """Issue #259: [CmdletBinding()] + Split-Path $PSScriptRoot in param() defaults crashes."""
    text = (ROOT / "scripts" / "Start-AircConsole.ps1").read_text(encoding="utf-8")
    assert "CmdletBinding" in text
    # Default expression must not call Split-Path on $PSScriptRoot inside param().
    assert "[string]$RepoRoot = ''" in text or '[string]$RepoRoot = ""' in text
    assert "Split-Path $PSScriptRoot -Parent)," not in text
    assert "Get-AircConsoleScriptDir" in text or "PSCommandPath" in text
    assert "FR #259" in text
    # $Home is a read-only automatic variable â€” parameter must be ConsoleHome.
    assert "[string]$Home" not in text
    assert "$ConsoleHome" in text
    install = (ROOT / "scripts" / "Install-AircConsole.ps1").read_text(encoding="utf-8")
    assert "FR #259" in install
    assert "[string]$Home" not in install
    assert "ConsoleHome" in install
    assert "powershell.exe" in install


def test_fr266_bundled_nssm_in_release_and_install_resolver():
    """FR #266: pack ships third_party/nssm; install prefers it over C:\\ai\\ergo."""
    nssm = ROOT / "third_party" / "nssm" / "win64" / "nssm.exe"
    assert nssm.is_file(), "bundled nssm.exe missing from repo"
    assert nssm.stat().st_size > 10000
    pack = (ROOT / "scripts" / "Pack-AircConsoleRelease.ps1").read_text(encoding="utf-8")
    assert r"third_party\nssm\win64\nssm.exe" in pack
    install = (ROOT / "scripts" / "Install-AircConsole.ps1").read_text(encoding="utf-8")
    assert "Resolve-AircNssm" in install
    assert "third_party" in install
    assert "FR #266" in install
    # Default param must not hard-require C:\\ai\\ergo only
    assert "[string]$Nssm = 'C:\\ai\\ergo\\nssm.exe'" not in install
    assert (ROOT / "src" / "airc_console" / "VERSION").read_text(encoding="utf-8").strip() == "0.1.4"
    readme = (ROOT / "src" / "airc_console" / "README.md").read_text(encoding="utf-8")
    assert "FR #266" in readme
    docs = (ROOT / "docs" / "airc-console-fr253.md").read_text(encoding="utf-8")
    assert "FR #259" in docs


def test_service_selftest_subprocess():
    import subprocess

    py = sys.executable
    script = SCRIPTS / "airc_console_service.py"
    proc = subprocess.run([py, str(script), "--selftest"], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "selftest ok" in proc.stdout


def test_pack_script_mentions_zip():
    text = (ROOT / "scripts" / "Pack-AircConsoleRelease.ps1").read_text(encoding="utf-8")
    assert "airc-console-" in text
    assert "Compress-Archive" in text

