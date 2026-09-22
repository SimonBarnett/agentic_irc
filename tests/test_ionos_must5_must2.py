from __future__ import annotations

import json
import py_compile
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bobstat
import bobtalk
import grok_talk

ROOT = Path(__file__).resolve().parents[1]
FIX = Path(__file__).resolve().parent / "fixtures"
SPAWN = ROOT / "scripts" / "start_worker_irc_agent.py"
LIVE = FIX / "ionos-peer-live-2026-09-21.json"
POINT = FIX / "ionos-peer-point-written.json"


def test_live_ionos_peer_without_remaining_cannot_grok_talk(tmp_path):
    """Baseline live shape (no remaining_*): cannot grok-talk (cursor_label ignored)."""
    doc = json.loads(LIVE.read_text(encoding="utf-8"))
    bobstat.write_peer(tmp_path, doc)
    assert grok_talk.fuel_ok(tmp_path, "ionos") is False
    line = bobtalk.mention_reply_line(
        tmp_path, "ionos", ["bob-ionos"], "simon", "@bob-ionos status?"
    )
    assert "cannot grok-talk" in line


def test_point_written_ionos_peer_fuel_ok_no_cannot(tmp_path):
    """Peer bytes from BOB POINT remaining= (ConvertFrom/write_peer), not hand-typed remaining."""
    raw = POINT.read_text(encoding="utf-8")
    doc = json.loads(raw)
    assert doc.get("remaining_pct") == 82
    bobstat.write_peer(tmp_path, doc)
    assert grok_talk.fuel_ok(tmp_path, "ionos") is True
    line = bobtalk.mention_reply_line(
        tmp_path, "ionos", ["bob-ionos"], "simon", "@bob-ionos status?"
    )
    assert line is not None
    assert "cannot grok-talk" not in line
    assert "weekly=0 (cursor remaining=82%)" in line


def test_parse_point_remaining_lands_on_peer_aliases(tmp_path):
    line = (
        "BOB v1 id=ionos weekly=0 running=1 queued=1 "
        "lastSeen=2026-09-22T18:30:00Z jobs=- remaining=82"
    )
    doc = bobstat.parse_bob_point(line)
    bobstat.write_peer(tmp_path, doc)
    got = bobstat.read_peer(tmp_path, "ionos")
    assert got["remaining_pct"] == 82
    assert got["account_remaining_pct"] == 82
    assert got["cursor_remaining_pct"] == 82
    assert grok_talk.fuel_ok(tmp_path, "ionos") is True


def test_write_peer_preserves_remaining_across_bare_point(tmp_path):
    bobstat.write_peer(
        tmp_path,
        bobstat.parse_bob_point(
            "BOB v1 id=ionos weekly=0 running=0 queued=0 lastSeen=t jobs=- remaining=82"
        ),
    )
    bare = bobstat.parse_bob_point(
        "BOB v1 id=ionos weekly=0 running=1 queued=0 lastSeen=u jobs=-"
    )
    bobstat.write_peer(tmp_path, bare)
    kept = bobstat.read_peer(tmp_path, "ionos")
    assert kept["remaining_pct"] == 82
    assert kept["weekly"] == 0


def test_start_worker_irc_agent_utf8_py_compile_and_dry_run(tmp_path, monkeypatch):
    raw = SPAWN.read_bytes()
    assert raw.count(0) == 0
    assert raw.startswith(b"#!/usr/bin/env python")
    py_compile.compile(str(SPAWN), doraise=True)
    monkeypatch.setenv("BOB_IRC_HOME", str(tmp_path))
    workers = tmp_path / "workers" / "ionos" / "4412"
    assert not workers.exists()
    proc = subprocess.run(
        [
            sys.executable,
            str(SPAWN),
            "--dry-run",
            "--fleet-home",
            str(tmp_path),
            "--machine-id",
            "ionos",
            "--pid",
            "4412",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    out = proc.stdout
    assert "w-io-4412" in out
    assert "#ionos" in out
    assert not workers.exists(), "dry-run must not mkdir worker home"
