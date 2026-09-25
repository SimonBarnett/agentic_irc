"""Jeeves keep-alive task: runs as the chair user, one instance == one chair."""
from __future__ import annotations

from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "Register-BobChairTask.ps1"


def _text() -> str:
    return SCRIPT.read_text(encoding="utf-8-sig")


def test_task_launches_install_bob_chair_from_same_checkout():
    text = _text()
    assert "Join-Path $here 'Install-BobChair.ps1'" in text
    assert "--host $IrcHost --port $Port" in text


def test_task_is_a_watchdog_single_instance():
    text = _text()
    assert "-MultipleInstances IgnoreNew" in text
    assert "-RepetitionInterval (New-TimeSpan -Minutes $WatchMinutes)" in text
    assert "[int]$WatchMinutes = 1" in text
    assert "-AtLogOn" in text
    assert "-ExecutionTimeLimit ([TimeSpan]::Zero)" in text


def test_task_runs_as_interactive_user_not_localsystem():
    """DPAPI identity + icacls(USERDOMAIN\\USERNAME) fail as SYSTEM (icacls 1332)."""
    text = _text()
    assert "-LogonType Interactive" in text
    assert "$env:USERNAME -like '*$'" in text  # refuses machine/service accounts
    assert "ServiceAccount" not in text


def test_task_has_own_log_and_no_password():
    text = _text()
    assert "bobjeeves-chair-task.log" in text
    lowered = text.lower()
    assert "-password" not in lowered
    assert "connect.password" not in lowered


def test_mrb_defaults_and_principal_are_fleet_chair_safe():
    """Hostile: fleet Ergo defaults, Highest interactive, no NSSM, missing chair throws."""
    text = _text()
    assert "[string]$IrcHost = 'irc.ntsa.uk'" in text
    assert "[int]$Port = 6697" in text
    assert "[string]$TaskName = 'BobJeeves-chair'" in text
    assert "-RunLevel Highest" in text
    assert "New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive" in text
    assert "Register-ScheduledTask" in text and "-Force" in text
    # Body must not shell out to nssm (comment may mention NSSM as the problem)
    body = text.split("#Requires", 1)[-1]
    assert "nssm" not in body.lower()
    assert "missing $chair" in text
    assert "long-running-background-tasks" in text
    # Watchdog: logon + repeating Once; IgnoreNew so one chair lifetime per instance
    assert "New-ScheduledTaskTrigger -AtLogOn" in text
    assert "New-ScheduledTaskTrigger -Once" in text
    assert "RepetitionDuration (New-TimeSpan -Days 9999)" in text


def test_mrb_start_now_is_opt_in_only():
    text = _text()
    assert "[switch]$StartNow" in text
    assert "if ($StartNow)" in text
    assert "Start-ScheduledTask -TaskName $TaskName" in text
    # Default path must not auto-start without the switch (Start-ScheduledTask only inside if)
    after = text.split("if ($StartNow)", 1)[1]
    before = text.split("if ($StartNow)", 1)[0]
    assert "Start-ScheduledTask" in after
    assert "Start-ScheduledTask" not in before
