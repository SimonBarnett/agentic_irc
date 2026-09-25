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
