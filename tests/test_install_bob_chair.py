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

def test_install_bob_chair_clears_stale_quit_request_before_launch():
    """A force-killed prior chair leaves agent.quit.request; new Jeeves must not eat it."""
    text = SCRIPT.read_text(encoding="utf-8-sig")
    stop = text.index("\nStop-PriorChair -Nick $nick")
    launch = text.index("& python $py")
    clear = text.find("Remove-Item -LiteralPath $staleQuit")
    assert clear != -1, "stale agent.quit.request is never removed"
    assert stop < clear < launch
    assert "$staleQuit = Join-Path $chairHome 'agent.quit.request'" in text


def test_mrb_stale_quit_clear_is_only_agent_quit_request_file():
    """Hostile: clear targets agent.quit.request only, not the whole chair home."""
    text = SCRIPT.read_text(encoding="utf-8-sig")
    assert "Join-Path $chairHome 'agent.quit.request'" in text
    # Must not wipe home or delete arbitrary files
    assert "Remove-Item -LiteralPath $chairHome" not in text
    assert "Remove-Item -Recurse" not in text.split("Stop-PriorChair -Nick $nick", 1)[-1].split(
        "& python $py", 1
    )[0]


def test_mrb_stale_quit_clear_before_persist_and_launch():
    """Hostile: clear after Stop-PriorChair and before persist_chair_nick + launch."""
    text = SCRIPT.read_text(encoding="utf-8-sig")
    stop = text.index("Stop-PriorChair -Nick $nick")
    clear = text.index("Remove-Item -LiteralPath $staleQuit")
    persist = text.index("persist_chair_nick")
    launch = text.index("& python $py")
    assert stop < clear < persist < launch


def test_mrb_stop_prior_still_writes_quit_request_for_graceful_old_chair():
    """Graceful path still asks the old chair to quit; only the leftover is cleared."""
    text = SCRIPT.read_text(encoding="utf-8-sig")
    req = text[text.index("function Request-ChairQuit") : text.index("function Stop-PriorChair")]
    assert "agent.quit.request" in req
    assert "Request-ChairQuit" in text[text.index("function Stop-PriorChair") :]
