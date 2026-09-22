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
