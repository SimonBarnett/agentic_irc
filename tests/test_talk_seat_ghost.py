from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import talk_seat_ghost as tsg  # noqa: E402


def test_discover_talk_seat_homes_flamingo(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(tsg.Path, "home", lambda: tmp_path)
    home = tmp_path / ".agentic-irc-cursor"
    home.mkdir()
    (home / "coordinator.pid").write_text(
        "nick=flamingo-12345\nseat=999\nagent=1\nhome=" + str(home) + "\n",
        encoding="utf-8",
    )
    found = tsg.discover_talk_seat_homes("flamingo")
    assert home in found


def test_ghost_prune_skips_live_agent(tmp_path: Path, monkeypatch):
    home = tmp_path / "seat"
    home.mkdir()
    (home / "coordinator.pid").write_text("nick=flamingo-55\nseat=1\n", encoding="utf-8")
    monkeypatch.setattr(tsg.agent_control, "find_irc_agent_pid", lambda _h: 4242)
    called = {"n": 0}

    def _ghost(*_a, **_k):
        called["n"] += 1
        return True

    monkeypatch.setattr(tsg.ergo_brief, "ghost_quit_session", _ghost)
    out = tsg.ghost_prune_homes("flamingo", "irc.ntsa.uk", 6697, "pw", homes=[home])
    assert out == []
    assert called["n"] == 0


def test_ghost_prune_calls_quit_when_no_agent(tmp_path: Path, monkeypatch):
    home = tmp_path / "seat"
    home.mkdir()
    (home / "coordinator.pid").write_text("nick=flamingo-55\nseat=1\n", encoding="utf-8")
    monkeypatch.setattr(tsg.agent_control, "find_irc_agent_pid", lambda _h: None)
    monkeypatch.setattr(tsg.ergo_brief, "ghost_quit_session", lambda *_a, **_k: True)
    out = tsg.ghost_prune_homes("flamingo", "irc.ntsa.uk", 6697, "pw", homes=[home])
    assert out == ["flamingo-55"]


def test_ergo_dead_tcp_bound_default():
    assert tsg.ergo_dead_tcp_names_s() >= 60.0
