from __future__ import annotations

from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "Install-BobChair.ps1"


def test_install_bob_chair_splits_jeeves_home_and_digest_home():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "$chairHome = Join-Path $env:USERPROFILE '.agentic-irc-jeeves'" in text
    assert "$digestHome = Join-Path $env:USERPROFILE '.agentic-irc-bobiverse'" in text
    assert "$env:AGENTIC_IRC_HOME = $chairHome" in text
    assert "$env:BOB_DIGEST_HOME = $digestHome" in text
    assert "--home $chairHome" in text
    assert "if ($env:AGENTIC_IRC_HOME)" not in text
    assert "'Jeeves'" in text
    assert "connect.password" in text
    assert "irc_agent.py" in text
    assert "--chair" in text
    launch = [
        ln
        for ln in text.splitlines()
        if ln.strip().startswith("& python $py")
    ]
    assert len(launch) == 1
    assert "--password" not in launch[0]
    assert "--home $chairHome" in launch[0]
    assert ".agentic-irc-bobiverse" not in launch[0]
