"""FR #341: bob-* must not IRC-announce idle/busy; digest owns worker state."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bobstat
import bobtalk


def test_peer_talk_lines_never_idle_busy(tmp_path):
    bobstat.write_peer(
        tmp_path,
        {"ok": True, "id": "marchhare", "weekly": 1, "running": 0, "queued": 0, "jobs": []},
    )
    bobstat.write_peer(
        tmp_path,
        {
            "ok": True,
            "id": "ionos",
            "weekly": 1,
            "running": 1,
            "queued": 0,
            "model": "Cursor Models",
            "kind": "mrb",
            "repo": "SimonBarnett/agentic_build",
            "jobs": [{"repo": "SimonBarnett/agentic_build", "state": "running"}],
        },
    )
    for mid in ("marchhare", "ionos"):
        lines = bobtalk.peer_talk_lines(bobstat.read_peer(tmp_path, mid))
        assert lines == []
        blob = " ".join(lines).lower()
        assert "is idle" not in blob
        assert "is busy" not in blob


def test_network_and_change_talk_silent(tmp_path):
    bobstat.write_peer(
        tmp_path,
        {"ok": True, "id": "flamingo", "running": 0, "queued": 0, "jobs": []},
    )
    assert bobtalk.network_talk_lines(tmp_path) == []
    before = {"id": "flamingo", "running": 0, "queued": 0, "jobs": []}
    after = {
        "id": "flamingo",
        "running": 1,
        "queued": 0,
        "kind": "git",
        "repo": "SimonBarnett/x",
        "jobs": [{"repo": "SimonBarnett/x", "state": "running"}],
    }
    assert bobtalk.change_talk_line(None, after) is None
    assert bobtalk.change_talk_line(before, after) is None


def test_mention_ack_no_idle_busy_status(tmp_path):
    bobstat.write_peer(
        tmp_path,
        {"ok": True, "id": "ionos", "weekly": 0, "running": 0, "queued": 0, "jobs": []},
    )
    line = bobtalk.mention_reply_line(
        tmp_path, "ionos", ["bob-ionos"], "cursor-flamingo", "@bob-ionos align shop-channel?"
    )
    assert line is not None
    assert line.startswith("@cursor-flamingo ionos here.")
    assert "weekly=0 (cannot grok-talk)" in line
    assert "Heard:" in line
    low = line.lower()
    assert " is idle" not in low
    assert " is busy" not in low
    assert "working on" not in low
    assert " is on " not in low


def test_src_bobtalk_has_no_idle_busy_string_literals():
    src = (Path(__file__).resolve().parents[1] / "scripts" / "bobtalk.py").read_text(
        encoding="utf-8"
    )
    # Implementation must not construct status phrases for IRC emission.
    assert 'f"{mid} is idle."' not in src
    assert 'f"{mid} is busy."' not in src
    assert 'return [f"{mid} is idle."]' not in src
    assert 'return lines or [f"{mid} is busy."]' not in src
    assert "is on {model}" not in src
    assert "Working on {repo}" not in src or "FR #341" in src
