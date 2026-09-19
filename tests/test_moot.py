from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import irc_agent
import moot
import seal
import wire

MID = "0123456789abcdef"


def _open(chair="grok-box-a"):
    line = wire.parse_moot_line(f"MOOT v1 OPEN {MID} {chair} floor :cut over file server")
    return moot.apply_moot({}, chair, line)


def _args(home: Path, nick: str = "grok-box-a") -> argparse.Namespace:
    return argparse.Namespace(
        nick=nick,
        channel="#ops",
        home=str(home),
        outbox="",
        hello="",
        announce_key=False,
        host="127.0.0.1",
        port=6697,
        realname="test",
        once=True,
    )


def test_open_join_roster():
    st = _open()
    st = moot.apply_moot(st, "claude-box", wire.parse_moot_line(f"MOOT v1 JOIN {MID}"))
    st = moot.apply_moot(st, "srv2012-box", wire.parse_moot_line(f"MOOT v1 JOIN {MID}"))
    st = moot.apply_moot(st, "grok-box-a", wire.parse_moot_line(f"MOOT v1 ROSTER {MID} :grok-box-a,claude-box,srv2012-box"))
    assert st["state"] == "open"
    assert len(st["roster"]) == 3
    assert st["roster"] == ["grok-box-a", "claude-box", "srv2012-box"]


def test_say_from_non_floor_dropped(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    st = _open()
    st = moot.apply_moot(st, "claude-box", wire.parse_moot_line(f"MOOT v1 JOIN {MID}"))
    st = moot.apply_moot(st, "srv2012-box", wire.parse_moot_line(f"MOOT v1 JOIN {MID}"))
    st = moot.apply_moot(st, "grok-box-a", wire.parse_moot_line(f"MOOT v1 FLOOR {MID} grok-box-a"))
    st = moot.apply_moot(st, "claude-box", wire.parse_moot_line(f"MOOT v1 SAY {MID} 1 :nope"), tmp_path)
    st = moot.apply_moot(st, "srv2012-box", wire.parse_moot_line(f"MOOT v1 SAY {MID} 1 :listener"), tmp_path)
    st = moot.apply_moot(st, "grok-box-a", wire.parse_moot_line(f"MOOT v1 SAY {MID} 1 :floor-ok"), tmp_path)
    tx = tmp_path / "moot" / f"{MID}.txt"
    text = tx.read_text() if tx.exists() else ""
    assert "nope" not in text
    assert "listener" not in text
    assert "floor-ok" in text
    assert st["floor"] == "grok-box-a"


def test_three_nick_floor_via_privmsg(tmp_path, monkeypatch):
    """PDF Phase 2 exit / M2–M3: listener that never held the floor emits zero SAY lines."""
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    seal.genkey()
    c = irc_agent.Client(_args(tmp_path, "grok-box-a"))
    c.handle_privmsg("grok-box-a!u@h", "#ops", f"MOOT v1 OPEN {MID} grok-box-a floor :cut over file server")
    c.handle_privmsg("claude-box!u@h", "#ops", f"MOOT v1 JOIN {MID}")
    c.handle_privmsg("srv2012-box!u@h", "#ops", f"MOOT v1 JOIN {MID}")
    c.handle_privmsg("grok-box-a!u@h", "#ops", f"MOOT v1 FLOOR {MID} claude-box")
    c.handle_privmsg("claude-box!u@h", "#ops", f"MOOT v1 SAY {MID} 1 :speaker")
    c.handle_privmsg("srv2012-box!u@h", "#ops", f"MOOT v1 SAY {MID} 1 :nope")
    c.handle_privmsg("claude-box!u@h", "#ops", f"MOOT v1 YIELD {MID} *")
    c.handle_privmsg("grok-box-a!u@h", "#ops", f"MOOT v1 CLOSE {MID} :done")
    st = c._moot
    assert st["state"] == "closed"
    assert len(st["roster"]) == 3
    tx = (tmp_path / "moot" / f"{MID}.txt").read_text()
    assert "speaker" in tx
    assert "nope" not in tx
    c.handle_privmsg("grok-box-a!u@h", "#ops", f"MOOT v1 SAY {MID} 2 :after")
    tx2 = (tmp_path / "moot" / f"{MID}.txt").read_text()
    assert "after" not in tx2


def test_floor_say_yield_close(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    home = tmp_path
    st = _open()
    st = moot.apply_moot(st, "claude-box", wire.parse_moot_line(f"MOOT v1 JOIN {MID}"))
    st = moot.apply_moot(st, "grok-box-a", wire.parse_moot_line(f"MOOT v1 FLOOR {MID} grok-box-a"))
    st = moot.apply_moot(st, "grok-box-a", wire.parse_moot_line(f"MOOT v1 SAY {MID} 1 :hello"), home)
    st = moot.apply_moot(st, "grok-box-a", wire.parse_moot_line(f"MOOT v1 YIELD {MID} *"))
    assert st["floor"] is None
    st = moot.apply_moot(st, "grok-box-a", wire.parse_moot_line(f"MOOT v1 CLOSE {MID} :done"), home)
    assert st["state"] == "closed"
    st = moot.apply_moot(st, "grok-box-a", wire.parse_moot_line(f"MOOT v1 SAY {MID} 2 :after"), home)
    tx = (home / "moot" / f"{MID}.txt").read_text()
    assert "after" not in tx


def test_handoff_not_on_roster():
    st = _open()
    st = moot.apply_moot(st, "grok-box-a", wire.parse_moot_line(f"MOOT v1 HANDOFF {MID} stranger"))
    assert st["chair"] == "grok-box-a"


def test_part_clears_floor():
    st = _open()
    st["floor"] = "grok-box-a"
    st = moot.apply_moot(st, "grok-box-a", wire.parse_moot_line(f"MOOT v1 PART {MID} :bye"))
    assert st["floor"] is None


def test_two_opens_first_wins():
    st = _open("grok-box-a")
    st2 = moot.apply_moot(st, "claude-box", wire.parse_moot_line(f"MOOT v1 OPEN {MID} claude-box floor :other"))
    assert st2["chair"] == "grok-box-a"


def test_seq_must_increase(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    st = _open()
    st["floor"] = "grok-box-a"
    st = moot.apply_moot(st, "grok-box-a", wire.parse_moot_line(f"MOOT v1 SAY {MID} 2 :a"), tmp_path)
    st = moot.apply_moot(st, "grok-box-a", wire.parse_moot_line(f"MOOT v1 SAY {MID} 2 :b"), tmp_path)
    tx = (tmp_path / "moot" / f"{MID}.txt").read_text()
    assert tx.count("SAY") == 1


def test_chair_roster_and_transcript_without_own_privmsg_echo(tmp_path, monkeypatch):
    """Libera does not echo own PRIVMSG. Chair CLI writes OPEN/FLOOR/CLOSE to disk;
    JOINA from other nicks arrives only via handle_privmsg on an empty in-memory _moot."""
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    seal.genkey()
    parsed = wire.parse_moot_line(f"MOOT v1 OPEN {MID} grok-box-a floor :mode2 SEAL+FILE probe")
    st = moot.apply_moot({}, "grok-box-a", parsed, tmp_path)
    assert st["roster"] == ["grok-box-a"]

    c = irc_agent.Client(_args(tmp_path, "grok-box-a"))
    assert c._moot == {}
    c.handle_privmsg("claude-box!u@h", "#ops", f"MOOT v1 JOIN {MID}")
    c.handle_privmsg("srv2012-box!u@h", "#ops", f"MOOT v1 JOIN {MID}")
    disk = moot.load_state(tmp_path, MID)
    assert disk["roster"] == ["grok-box-a", "claude-box", "srv2012-box"]
    assert disk["state"] == "open"

    parsed = wire.parse_moot_line(f"MOOT v1 FLOOR {MID} claude-box")
    st = moot.apply_moot(moot.load_state(tmp_path, MID), "grok-box-a", parsed, tmp_path)
    assert st["floor"] == "claude-box"
    disk = moot.load_state(tmp_path, MID)
    assert disk["floor"] == "claude-box"
    assert disk["roster"] == ["grok-box-a", "claude-box", "srv2012-box"]

    c.handle_privmsg("claude-box!u@h", "#ops", f"MOOT v1 SAY {MID} 1 :speaker")
    disk = moot.load_state(tmp_path, MID)
    assert disk["seq_by_nick"]["claude-box"] == 1
    assert disk["floor"] == "claude-box"

    c.handle_privmsg("claude-box!u@h", "#ops", f"MOOT v1 YIELD {MID} *")
    disk = moot.load_state(tmp_path, MID)
    assert disk["floor"] is None

    parsed = wire.parse_moot_line(f"MOOT v1 CLOSE {MID} :mode2 moot exercised")
    st = moot.apply_moot(moot.load_state(tmp_path, MID), "grok-box-a", parsed, tmp_path)
    disk = moot.load_state(tmp_path, MID)
    assert disk["state"] == "closed"
    assert disk["floor"] is None
    assert disk["roster"] == ["grok-box-a", "claude-box", "srv2012-box"]
    assert disk["seq_by_nick"]["claude-box"] == 1

    tx = (tmp_path / "moot" / f"{MID}.txt").read_text()
    for verb in ("OPEN", "JOIN", "FLOOR", "SAY", "YIELD", "CLOSE"):
        assert verb in tx, verb
    assert "speaker" in tx
    assert tx.count("JOIN") == 2
