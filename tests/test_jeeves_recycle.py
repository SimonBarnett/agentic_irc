from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bob_recycle
import bobreport
import bobtalk
import irc_agent


@pytest.fixture
def recorder(monkeypatch):
    lines: list[str] = []

    def capture(self, line: str) -> None:
        lines.append(line)

    monkeypatch.setattr(irc_agent.Client, "send", capture)

    def whisper(self, nick: str, text: str) -> None:
        lines.append(f"PRIVMSG {nick} :{text}")

    monkeypatch.setattr(irc_agent.Client, "whisper", whisper)
    return lines


def _args(home: Path, nick: str, *, chair: bool = False) -> argparse.Namespace:
    return argparse.Namespace(
        nick=nick,
        channel="#bobiverse",
        home=str(home),
        outbox="",
        hello="",
        announce_key=False,
        host="127.0.0.1",
        port=6697,
        realname="test",
        once=True,
        password="",
        chair=chair,
    )


def test_chair_handles_recycle_ionos(tmp_path, recorder, monkeypatch):
    bobreport.persist_chair_nick(tmp_path, "Jeeves")
    executed: list[str] = []

    def fake_exec(mid, home, *, ionos_chair=False, hooks=None):
        executed.append(mid)
        return bob_recycle.build_recycle_plan(mid, ionos_chair=ionos_chair)

    monkeypatch.setattr(irc_agent.bob_recycle, "execute_local_recycle", fake_exec)
    chair = irc_agent.Client(_args(tmp_path, "Jeeves", chair=True))
    chair.handle_privmsg("simon!u@h", "#bobiverse", "!recycle ionos")

    assert executed == ["ionos"]
    assert any("started ionos" in x for x in recorder)
    assert not any("RECYCLE v1" in x for x in recorder)
    assert (tmp_path / "agent.quit.request").is_file()


def test_bob_ignores_recycle_command(tmp_path, recorder):
    bob = irc_agent.Client(_args(tmp_path, "bob-flamingo"))
    bob.handle_privmsg("simon!u@h", "#bobiverse", "!recycle flamingo")
    assert recorder == []


def test_chair_wire_remote_machine(tmp_path, recorder):
    bobreport.persist_chair_nick(tmp_path, "Jeeves")
    chair = irc_agent.Client(_args(tmp_path, "Jeeves", chair=True))
    chair.handle_privmsg("simon!u@h", "#bobiverse", "!recycle flamingo")
    assert any("PRIVMSG #bobiverse :RECYCLE v1 flamingo" in x for x in recorder)
    assert any("requested flamingo" in x for x in recorder)


def test_chair_refuse_unknown(tmp_path, recorder):
    bobreport.persist_chair_nick(tmp_path, "Jeeves")
    chair = irc_agent.Client(_args(tmp_path, "Jeeves", chair=True))
    chair.handle_privmsg("simon!u@h", "#bobiverse", "!recycle nope")
    assert any("refused unknown" in x for x in recorder)
    assert not any("RECYCLE v1" in x for x in recorder)


def test_bob_executes_recycle_wire_from_chair(tmp_path, recorder, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    monkeypatch.setenv("AGENTIC_IRC_CHAIR_NICK", "bob-chair")
    bobreport.persist_chair_nick(tmp_path, "bob-chair")
    executed: list[str] = []

    def fake_exec(mid, home, *, ionos_chair=False, hooks=None):
        executed.append(mid)
        return bob_recycle.build_recycle_plan(mid, ionos_chair=ionos_chair)

    monkeypatch.setattr(irc_agent.bob_recycle, "execute_local_recycle", fake_exec)
    bob = irc_agent.Client(_args(tmp_path, "bob-flamingo"))
    bob.handle_privmsg("bob-chair!u@h", "#bobiverse", "RECYCLE v1 flamingo")
    assert executed == ["flamingo"]


def test_bobiverse_unchanged_after_recycle_parser(tmp_path, monkeypatch, recorder):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    bobreport.persist_chair_nick(tmp_path, "bob-chair")
    chair = irc_agent.Client(_args(tmp_path, "bob-chair", chair=True))
    chair.handle_privmsg("simon!u@h", "#bobiverse", "!bobiverse")
    assert any(bobreport.BOBIVERSE_GONE in x for x in recorder)
