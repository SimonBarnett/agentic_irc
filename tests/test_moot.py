from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import moot
import wire

MID = "0123456789abcdef"


def _open(chair="grok-box-a"):
    line = wire.parse_moot_line(f"MOOT v1 OPEN {MID} {chair} floor :cut over file server")
    return moot.apply_moot({}, chair, line)


def test_open_join_roster():
    st = _open()
    st = moot.apply_moot(st, "claude-box", wire.parse_moot_line(f"MOOT v1 JOIN {MID}"))
    st = moot.apply_moot(st, "srv2012-box", wire.parse_moot_line(f"MOOT v1 JOIN {MID}"))
    assert st["state"] == "open"
    assert len(st["roster"]) == 3


def test_say_from_non_floor_dropped(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    st = _open()
    st["floor"] = "grok-box-a"
    st = moot.apply_moot(st, "claude-box", wire.parse_moot_line(f"MOOT v1 SAY {MID} 1 :nope"), tmp_path)
    tx = tmp_path / "moot" / f"{MID}.txt"
    assert not tx.exists() or "nope" not in tx.read_text()


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
