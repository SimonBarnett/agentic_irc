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
    ensure_nickserv_password,
    load_operators,
    machine_id,
    resolve_server_password,
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
    # #266: do not hard-default to fleet-only C:\ai\ergo\nssm.exe
    assert "Resolve-AircConsoleNssm" in install
    assert "third_party" in install
    # #273: tear down prior service; nssm stderr must not abort Stop
    assert "Remove-AircConsoleService" in install
    assert "Invoke-AircNssm" in install
    assert "remove" in install and "confirm" in install
    # #277: seed ergo.password from fleet connect.password + Start-Service
    assert "Initialize-AircConsoleHomeSecrets" in install
    assert "ergo.password" in install
    assert "connect.password" in install
    assert "Start-Service" in install
    assert "-NoStart" in install
    # #282: bake absolute python for LocalSystem
    assert "Resolve-AircConsolePython" in install
    assert '-Python' in install
    start = (ROOT / "scripts" / "Start-AircConsole.ps1").read_text(encoding="utf-8")
    assert "Resolve-AircConsolePython" in start
    assert "Issue #282" in start
    assert (ROOT / "scripts" / "Resolve-AircConsolePython.ps1").is_file()
    docs = (ROOT / "docs" / "airc-console-fr253.md").read_text(encoding="utf-8")
    assert "FR #259" in docs
    assert "#266" in docs or "issue #266" in docs


def test_ensure_nickserv_password_mints_guid_and_reuses(tmp_path: Path):
    """Issue #271: first start mints GUID; second start reuses same file."""
    path = tmp_path / "console.password"
    first = ensure_nickserv_password(path, mint=True)
    assert first
    assert path.is_file()
    # UUID shape
    assert len(first) >= 32
    assert "-" in first
    second = ensure_nickserv_password(path, mint=True)
    assert second == first


def test_resolve_server_password_ignores_console_password_guid(tmp_path: Path, monkeypatch):
    """NickServ GUID file must not be sent as Ergo server PASS."""
    home = tmp_path / "home"
    home.mkdir()
    guid = ensure_nickserv_password(home / "console.password", mint=True)
    assert guid
    monkeypatch.delenv("AIRC_CONSOLE_SERVER_PASSWORD", raising=False)
    monkeypatch.delenv("AGENTIC_IRC_PASSWORD", raising=False)
    monkeypatch.delenv("AIRC_CONSOLE_PASSWORD", raising=False)
    assert resolve_server_password(home=home, password_file=home / "console.password") is None
    ergo = home / "ergo.password"
    ergo.write_text("fleet-secret\n", encoding="utf-8")
    assert resolve_server_password(home=home, password_file=home / "console.password") == "fleet-secret"
    monkeypatch.setenv("AGENTIC_IRC_PASSWORD", "from-env")
    assert resolve_server_password(home=home) == "from-env"


def test_fr286_default_nick_and_433_recovery():
    """FR #286: console-<machine> default; 433 → machine suffix / unique retry."""
    from airc_console import default_console_nick, nick_after_433

    assert default_console_nick("flamingo") == "console-flamingo"
    assert default_console_nick("IONOS") == "console-ionos"
    assert nick_after_433("console", "flamingo") == "console-flamingo"
    alt = nick_after_433("console-flamingo", "flamingo")
    assert alt.startswith("console-flamingo-")
    assert alt != "console-flamingo"
    svc = (ROOT / "scripts" / "airc_console_service.py").read_text(encoding="utf-8")
    assert "nick_after_433" in svc
    assert 'cmd == "433"' in svc
    assert "default_console_nick" in svc
    start = (ROOT / "scripts" / "Start-AircConsole.ps1").read_text(encoding="utf-8")
    assert "FR #286" in start
    assert (ROOT / "src" / "airc_console" / "VERSION").read_text(encoding="utf-8").strip() == "0.1.10"


def test_nssm_resolve_prefers_bundled(tmp_path: Path):
    """Issue #266: bundled third_party nssm wins over missing C:\\ai\\ergo."""
    import subprocess

    scripts = tmp_path / "scripts"
    bundled = tmp_path / "third_party" / "nssm" / "win64"
    scripts.mkdir(parents=True)
    bundled.mkdir(parents=True)
    fake = bundled / "nssm.exe"
    fake.write_bytes(b"MZ-fake-nssm")
    resolve_src = (SCRIPTS / "Resolve-AircConsoleNssm.ps1").read_text(encoding="utf-8")
    (scripts / "Resolve-AircConsoleNssm.ps1").write_text(resolve_src, encoding="utf-8")
    ps = (
        f". '{scripts / 'Resolve-AircConsoleNssm.ps1'}'; "
        f"$p = Resolve-AircConsoleNssmPath -ScriptDir '{scripts}'; "
        "if (-not $p) { exit 2 }; Write-Output $p; exit 0"
    )
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = (proc.stdout or "").strip().splitlines()[-1]
    assert out.lower().endswith("nssm.exe")
    assert "third_party" in out.lower()


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
    assert "Fetch-Nssm" in text
    assert "third_party\\nssm\\win64" in text or "third_party/nssm/win64" in text

