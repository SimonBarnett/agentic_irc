"""FR #237: Start-TalkSeat.ps1 must start a fresh home without empty --nick."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TALK = (ROOT / "scripts" / "Start-TalkSeat.ps1").read_text(encoding="utf-8")


def test_script_has_auto_nick_and_refuses_empty_nick():
    assert "--auto-nick" in TALK
    assert "AGENTIC_IRC_SEAT_PID = 'self'" in TALK
    assert "Start-OneSeatAgent refuses empty" in TALK or "refuses empty --nick" in TALK
    assert "Assert-HomeBind requires a non-empty ExpectedNick" in TALK
    assert "Start-TalkAgent" not in TALK  # typo that called missing function
    assert "FR #237" in TALK


def test_first_bind_not_with_uninitialised_expected_nick():
    """The pre-fix bug: Assert-HomeBind/Start used $expectedNick before assignment."""
    # Strip comments
    lines = []
    for line in TALK.splitlines():
        s = line.lstrip()
        if s.startswith("#"):
            continue
        lines.append(line)
    body = "\n".join(lines)

    # First assignment of $expectedNick in executable code
    assign = re.search(r"\$expectedNick\s*=\s*", body)
    assert assign, "expectedNick must be assigned"
    first_bind = body.find("Assert-HomeBind")
    assert first_bind > 0
    # Any Assert-HomeBind before first $expectedNick = must pass a non-empty expression
    # (probeExpected / reuse path), never bare $expectedNick while still uninitialised.
    prefix = body[: assign.start()]
    for m in re.finditer(r"Assert-HomeBind[^\n]*", prefix):
        line = m.group(0)
        assert "ExpectedNick $expectedNick" not in line, (
            f"Assert-HomeBind used uninitialised $expectedNick: {line}"
        )
    for m in re.finditer(r"Start-OneSeatAgent[^\n]*", prefix):
        line = m.group(0)
        assert "NickToStart $expectedNick" not in line, (
            f"Start-OneSeatAgent used uninitialised $expectedNick: {line}"
        )


def test_fresh_start_uses_mid_zero_auto_nick():
    assert re.search(r'Start-OneSeatAgent\s+-NickToStart\s+"\$mid-0"\s+-AutoNick', TALK)
    assert "Start-OneSeatAgent" in TALK
    # AutoNick adds --auto-nick to argv
    assert "$argList += '--auto-nick'" in TALK or '+= "--auto-nick"' in TALK


def test_coordinator_write_uses_computed_nick():
    assert 'nick=$nick' in TALK
    assert "seat=$agentPid" in TALK
    assert "agent=$agentPid" in TALK


def test_survival_suite_still_expects_auto_nick():
    surv = (ROOT / "tests" / "test_talk_seat_survival.py").read_text(encoding="utf-8")
    assert '"--auto-nick" in talk' in surv
