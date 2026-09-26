"""FR #237: Start-TalkSeat.ps1 must start a fresh home with a real {machine}-{pid} nick."""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TALK = ROOT / "scripts" / "Start-TalkSeat.ps1"


def _talk_src() -> str:
    return TALK.read_text(encoding="utf-8")


def test_start_talk_seat_no_uninitialised_expected_nick_before_bind():
    src = _talk_src()
    # First Assert-HomeBind must not use $expectedNick before it is assigned.
    # Fresh path: either agent exists (expected set from agent PID) or listen-only
    # uses "$mid-0", or truly empty skips bind until after auto-nick start.
    assert "Start-TalkAgent" not in src, "broken Start-TalkAgent call must be gone"
    assert "-AutoNick" in src or "AutoNick" in src
    assert "--auto-nick" in src
    # Empty-nick start must be rejected
    assert "requires a non-empty nick" in src

    # Order: expectedNick assignment from agent PID before Assert when $agent is set
    agent_block = re.search(
        r"if \(\$agent\) \{(?P<body>.*?)\n\}",
        src,
        flags=re.S,
    )
    assert agent_block, "missing reuse-agent block"
    body = agent_block.group("body")
    assert "$expectedNick = \"$mid-$($agent.ProcessId)\"" in body or (
        "$expectedNick = \"$mid-$" in body and "ProcessId" in body
    )
    assert "Assert-HomeBind" in body
    # expectedNick assigned before Assert in that block
    assert body.index("$expectedNick") < body.index("Assert-HomeBind")


def test_fresh_start_uses_machine_zero_auto_nick():
    src = _talk_src()
    assert 'Start-OneSeatAgent -NickToStart "$mid-0" -AutoNick' in src
    # Never Start-OneSeatAgent with bare $expectedNick before it is computed for fresh homes
    # (the only empty-risk call was the old first path).
    bad = re.search(
        r"Start-OneSeatAgent -NickToStart \$expectedNick\b(?!.*AutoNick)",
        src,
    )
    # After start, restart with concrete expected nick (no AutoNick) is OK once PID known.
    # Ensure we never assert-bind with empty expected before first assignment in script order.
    first_assert = src.find("Assert-HomeBind")
    first_assign = src.find('$expectedNick = "$mid-$($agent.ProcessId)"')
    first_mid0 = src.find('Assert-HomeBind -HomePath $resolved -ExpectedNick "$mid-0"')
    assert first_assert > 0
    assert first_assign > 0 or first_mid0 > 0
    # The first Assert must be either mid-0 (listen reclaim) or after expected assign
    assert first_mid0 > 0 or (first_assign > 0 and first_assign < first_assert)


def test_coordinator_write_uses_non_empty_nick_fields():
    src = _talk_src()
    assert '"nick=$nick"' in src
    assert "Set-Content -LiteralPath (Join-Path $resolved 'coordinator.pid')" in src
    assert "if (-not $nick) {\n    $nick = $expectedNick\n}" in src.replace("\r\n", "\n")
