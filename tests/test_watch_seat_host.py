from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import talk_seat_pid  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _coord(home: Path, seat: int, agent: int) -> None:
    (home / "coordinator.pid").write_text(
        f"nick=marchhare-{seat}\nseat={seat}\nlisten=1\nagent={agent}\nhome={home}\n", encoding="utf-8"
    )


def test_watch_seat_nick_uses_live_monitor_pid(tmp_path: Path):
    # Watch-AgentHealth writes agent=<previous irc_agent>; restart must not crash-loop.
    _coord(tmp_path, 34992, 19864)
    assert talk_seat_pid.check_nick_seat_pid("marchhare-34992", 19864) is not None
    assert talk_seat_pid.watch_seat_host_ok("marchhare-34992", tmp_path, alive=lambda p: p == 34992)


def test_watch_seat_dead_monitor_or_other_suffix_refused(tmp_path: Path):
    _coord(tmp_path, 34992, 19864)
    assert not talk_seat_pid.watch_seat_host_ok("marchhare-34992", tmp_path, alive=lambda p: False)
    assert not talk_seat_pid.watch_seat_host_ok("marchhare-11111", tmp_path, alive=lambda p: True)
    assert not talk_seat_pid.watch_seat_host_ok("marchhare-34992", None, alive=lambda p: True)
    assert not talk_seat_pid.watch_seat_host_ok("bob-marchhare", tmp_path, alive=lambda p: True)


def test_irc_agent_main_accepts_watch_seat_host():
    src = (ROOT / "scripts" / "irc_agent.py").read_text(encoding="utf-8")
    assert "talk_seat_pid.watch_seat_host_ok(args.nick, home or None)" in src


def test_load_peers_unreadable_returns_empty(tmp_path: Path, monkeypatch):
    import seal

    p = tmp_path / "peers.json"
    p.write_text("{}", encoding="utf-8")

    def _deny(*_a, **_k):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(type(p), "read_text", _deny)
    assert seal.load_peers(p) == {}
