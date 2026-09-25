"""Seat reconnect hygiene: Ergo throttle backoff, recv-idle reconnect in place."""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import irc_agent  # noqa: E402
from test_offline_nick_liveness import _args  # noqa: E402


def test_is_connect_throttle_matches_ergo_text():
    assert irc_agent.is_connect_throttle(
        "You have attempted to connect too many times within a short duration. Wait a while"
    )
    assert irc_agent.is_connect_throttle("Connection throttled")
    assert not irc_agent.is_connect_throttle("Closing Link: ping timeout")
    assert not irc_agent.is_connect_throttle("")


def test_throttle_delay_grows_and_caps(monkeypatch):
    monkeypatch.delenv("AGENTIC_IRC_THROTTLE_BASE_S", raising=False)
    d = [irc_agent.throttle_delay_s(n) for n in range(1, 8)]
    assert d[0] == 120.0
    assert all(b >= a for a, b in zip(d, d[1:]))
    assert d[1] == 240.0
    assert max(d) == 900.0
    # hostile env values fall back / clamp
    monkeypatch.setenv("AGENTIC_IRC_THROTTLE_BASE_S", "junk")
    assert irc_agent.throttle_delay_s(1) == 120.0
    monkeypatch.setenv("AGENTIC_IRC_THROTTLE_BASE_S", "-5")
    assert irc_agent.throttle_delay_s(1) == 1.0


def test_recv_idle_reconnects_in_place_without_part(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    sent: list[str] = []
    monkeypatch.setattr(irc_agent.Client, "send", lambda self, line: sent.append(line))

    class _Sock:
        closed = False

        def close(self):
            self.closed = True

    c = irc_agent.Client(_args(tmp_path, "flamingo-100"))
    c.joined.set()
    s = _Sock()
    c.sock = s  # type: ignore[assignment]
    c._last_server_rx = time.time() - 999
    c.recv_idle_reconnect()
    assert s.closed
    assert c.dead.is_set()
    assert not c.stop.is_set(), "must not stop the process (monitor would relaunch)"
    assert not c._no_reconnect
    assert not any(x.startswith(("PART", "QUIT")) for x in sent)
    assert time.time() - c._last_server_rx < 5


def test_liveness_loop_uses_reconnect_for_recv_idle(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    monkeypatch.setattr(irc_agent.talk_seat_ghost, "seat_recv_idle_s", lambda: 0.01)
    monkeypatch.setattr(irc_agent.talk_seat_pid, "seat_liveness_poll_s", lambda: 0.01)
    monkeypatch.setattr(irc_agent.Client, "_seat_liveness_enabled", lambda self: True)
    monkeypatch.setattr(irc_agent.talk_seat_pid, "talk_seat_coordinator_gone", lambda *a: False)
    sent: list[str] = []
    monkeypatch.setattr(irc_agent.Client, "send", lambda self, line: sent.append(line))
    c = irc_agent.Client(_args(tmp_path, "flamingo-100"))
    c.joined.set()
    c.sock = None
    c._last_server_rx = time.time() - 5
    c.seat_liveness_loop()
    assert c.dead.is_set()
    assert not c.stop.is_set()
    assert not any(x.startswith("PART") for x in sent)

def test_mrb_recv_idle_sock_without_close(tmp_path: Path, monkeypatch):
    """Hostile: mock sock without .close must not raise; sock cleared."""
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    monkeypatch.setattr(irc_agent.Client, "send", lambda self, line: None)
    c = irc_agent.Client(_args(tmp_path, "marchhare-34992"))
    c.joined.set()
    c.sock = object()  # no close
    c.recv_idle_reconnect()
    assert c.sock is None
    assert c.dead.is_set()
    assert not c.stop.is_set()


def test_mrb_throttle_resets_on_001_source_lock():
    src = (ROOT / "scripts" / "irc_agent.py").read_text(encoding="utf-8")
    assert "is_connect_throttle(detail)" in src
    assert "self._throttled = True" in src
    assert "self._throttle_n = 0" in src
    assert "recv_idle_reconnect()" in src
    # pong path still QUIT (not reconnect)
    assert 'request_shutdown(":pong timeout")' in src
    assert "coordinator gone" in src.lower() or "talk_seat_coordinator_gone" in src


def test_mrb_throttle_delay_large_n_caps():
    assert irc_agent.throttle_delay_s(100) == 900.0
    assert irc_agent.throttle_delay_s(0) == 120.0  # treated as n=1 base
