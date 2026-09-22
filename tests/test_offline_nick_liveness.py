from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import irc_agent  # noqa: E402
import talk_seat_pid as tsp  # noqa: E402


def test_process_is_alive_current_pid():
    assert tsp.process_is_alive(__import__("os").getpid())


def test_talk_seat_coordinator_gone_uses_nick_suffix(tmp_path: Path):
    home = tmp_path / "seat"
    home.mkdir()
    assert not tsp.talk_seat_coordinator_gone(
        "flamingo-100", home, is_alive=lambda _p: True
    )
    assert tsp.talk_seat_coordinator_gone(
        "flamingo-100", home, is_alive=lambda _p: False
    )


def test_seat_liveness_disabled_for_bob_nick(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    c = irc_agent.Client(_args(tmp_path, "bob-ionos"))
    assert not c._seat_liveness_enabled()


def test_seat_liveness_disable_env_off(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    monkeypatch.setenv("AGENTIC_IRC_SEAT_LIVENESS", "off")
    c = irc_agent.Client(_args(tmp_path, "flamingo-100"))
    assert not c._seat_liveness_enabled()


def test_seat_liveness_not_disabled_by_default(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("AGENTIC_IRC_SEAT_LIVENESS", raising=False)
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    c = irc_agent.Client(_args(tmp_path, "flamingo-100"))
    assert c._seat_liveness_enabled()


def test_process_is_alive_dead_pid():
    assert not tsp.process_is_alive(999_999_999)


def test_seat_liveness_enabled_for_talk_seat(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    c = irc_agent.Client(_args(tmp_path, "flamingo-100"))
    assert c._seat_liveness_enabled()


def test_request_shutdown_sends_quit_and_skips_reconnect(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    sent: list[str] = []

    def _send(self, line: str) -> None:
        sent.append(line)

    monkeypatch.setattr(irc_agent.Client, "send", _send)
    c = irc_agent.Client(_args(tmp_path, "flamingo-100"))
    c.joined.set()
    c.sock = object()  # type: ignore[assignment]
    c.request_shutdown(":seat ended")
    assert any(x.startswith("QUIT ") for x in sent)
    assert c._no_reconnect
    assert c.stop.is_set()


def test_seat_liveness_loop_keeps_coordinator_alive(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    monkeypatch.setattr(irc_agent.talk_seat_pid, "seat_liveness_poll_s", lambda: 0.05)
    monkeypatch.setattr(
        irc_agent.talk_seat_pid,
        "talk_seat_coordinator_gone",
        lambda *_a, **_k: False,
    )
    c = irc_agent.Client(_args(tmp_path, "flamingo-100"))
    c.joined.set()
    c.sock = object()  # type: ignore[assignment]
    c._last_server_rx = time.time()
    t = threading.Thread(target=c.seat_liveness_loop, daemon=True)
    t.start()
    time.sleep(0.35)
    assert not c.stop.is_set()


def test_control_quit_request_triggers_shutdown(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    import agent_control

    agent_control.request_agent_quit(tmp_path, "recycle")
    sent: list[str] = []

    def _send(self, line: str) -> None:
        sent.append(line)

    monkeypatch.setattr(irc_agent.Client, "send", _send)
    c = irc_agent.Client(_args(tmp_path, "flamingo-100"))
    c.joined.set()
    c.sock = object()  # type: ignore[assignment]
    assert c._consume_control_quit()
    assert any(x.startswith("QUIT ") for x in sent)


def test_recv_idle_triggers_shutdown(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    monkeypatch.setattr(irc_agent.talk_seat_ghost, "seat_recv_idle_s", lambda: 0.01)
    sent: list[str] = []

    def _send(self, line: str) -> None:
        sent.append(line)

    monkeypatch.setattr(irc_agent.Client, "send", _send)
    c = irc_agent.Client(_args(tmp_path, "flamingo-100"))
    c.joined.set()
    c.sock = object()  # type: ignore[assignment]
    c._last_server_rx = time.time() - 5.0
    assert c._seat_recv_stale()
    c.request_shutdown(":recv idle")
    assert any("QUIT" in x for x in sent)


def test_pong_overdue_triggers_shutdown(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    monkeypatch.setattr(irc_agent.talk_seat_ghost, "pong_grace_s", lambda: 0.01)
    sent: list[str] = []

    def _send(self, line: str) -> None:
        sent.append(line)

    monkeypatch.setattr(irc_agent.Client, "send", _send)
    c = irc_agent.Client(_args(tmp_path, "flamingo-100"))
    c.joined.set()
    c.sock = object()  # type: ignore[assignment]
    c._pong_due_at = time.time() - 1.0
    assert c._seat_pong_overdue()
    c.request_shutdown(":pong timeout")
    assert any("QUIT" in x for x in sent)


def test_start_talk_seat_uses_agent_control_graceful_stop():
    text = (Path(__file__).resolve().parents[1] / "scripts" / "Start-TalkSeat.ps1").read_text(
        encoding="utf-8"
    )
    assert "agent_control.py" in text
    assert "--wait-s 12" in text
    assert "Start-Sleep -Milliseconds 600" not in text


def test_seat_liveness_loop_quits_on_recv_idle(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    monkeypatch.setattr(irc_agent.talk_seat_pid, "seat_liveness_poll_s", lambda: 0.05)
    monkeypatch.setattr(irc_agent.talk_seat_ghost, "seat_recv_idle_s", lambda: 0.01)
    monkeypatch.setattr(
        irc_agent.talk_seat_pid,
        "talk_seat_coordinator_gone",
        lambda *_a, **_k: False,
    )
    sent: list[str] = []

    def _send(self, line: str) -> None:
        sent.append(line)

    monkeypatch.setattr(irc_agent.Client, "send", _send)
    c = irc_agent.Client(_args(tmp_path, "flamingo-100"))
    c.joined.set()
    c.sock = object()  # type: ignore[assignment]
    c._last_server_rx = time.time() - 5.0
    t = threading.Thread(target=c.seat_liveness_loop, daemon=True)
    t.start()
    deadline = time.time() + 2.0
    while time.time() < deadline and not c.stop.is_set():
        time.sleep(0.02)
    assert c.stop.is_set()
    assert any("QUIT" in x for x in sent)


def test_seat_liveness_loop_quits_when_coordinator_gone(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    monkeypatch.setattr(irc_agent.talk_seat_pid, "seat_liveness_poll_s", lambda: 0.05)
    sent: list[str] = []

    def _send(self, line: str) -> None:
        sent.append(line)

    monkeypatch.setattr(irc_agent.Client, "send", _send)
    monkeypatch.setattr(
        irc_agent.talk_seat_pid,
        "talk_seat_coordinator_gone",
        lambda _nick, _home, **_: True,
    )
    c = irc_agent.Client(_args(tmp_path, "flamingo-100"))
    c.joined.set()
    c.sock = object()  # type: ignore[assignment]
    t = threading.Thread(target=c.seat_liveness_loop, daemon=True)
    t.start()
    deadline = time.time() + 2.0
    while time.time() < deadline and not c.stop.is_set():
        time.sleep(0.02)
    assert c.stop.is_set()
    assert any("QUIT" in x for x in sent)


def _args(home: Path, nick: str) -> object:
    import argparse

    return argparse.Namespace(
        nick=nick,
        channel="#bobiverse",
        home=str(home),
        outbox="",
        hello="",
        announce_key=False,
        chair=False,
        host="irc.ntsa.uk",
        port=6697,
        password="",
        realname="test",
        once=False,
        auto_nick=False,
    )
