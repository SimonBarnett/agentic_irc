from __future__ import annotations

import json
import py_compile
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bobstat
import bobtalk
import grok_talk

ROOT = Path(__file__).resolve().parents[1]
FIX = Path(__file__).resolve().parent / "fixtures"
SPAWN = ROOT / "scripts" / "start_worker_irc_agent.py"
LIVE = FIX / "ionos-peer-live-2026-09-21.json"
REFRESHED = FIX / "ionos-peer-watch-refreshed.json"


def test_live_ionos_peer_shape_cannot_grok_talk_without_remaining(tmp_path):
    """Replay of live bob-peers/ionos.json (no remaining_*): MUST 5 still red."""
    doc = json.loads(LIVE.read_text(encoding="utf-8"))
    bobstat.write_peer(tmp_path, doc)
    got = bobstat.read_peer(tmp_path, "ionos")
    assert got["weekly"] == 0
    assert got.get("cursor_label") == "82%"
    assert got.get("remaining_pct") in (None, "")
    assert grok_talk.fuel_ok(tmp_path, "ionos") is False
    line = bobtalk.mention_reply_line(
        tmp_path, "ionos", ["bob-ionos"], "simon", "@bob-ionos status?"
    )
    assert line is not None
    assert "cannot grok-talk" in line


def test_watch_refreshed_ionos_peer_fuel_ok_no_cannot(tmp_path):
    """Watch-refreshed copy: live shape + remaining_* aliases → fuel_ok, no cannot."""
    doc = json.loads(REFRESHED.read_text(encoding="utf-8"))
    bobstat.write_peer(tmp_path, doc)
    got = bobstat.read_peer(tmp_path, "ionos")
    assert got["remaining_pct"] == 82
    assert got["account_remaining_pct"] == 82
    assert got["cursor_remaining_pct"] == 82
    assert got.get("cursor_label") == "82%"
    assert grok_talk.fuel_ok(tmp_path, "ionos") is True
    assert grok_talk.cursor_remaining_ok(tmp_path, "ionos") is True
    line = bobtalk.mention_reply_line(
        tmp_path, "ionos", ["bob-ionos"], "simon", "@bob-ionos status?"
    )
    assert line is not None
    assert "cannot grok-talk" not in line
    assert "weekly=0 (cursor remaining=82%)" in line


def test_write_peer_expands_remaining_aliases_and_preserves(tmp_path):
    bobstat.write_peer(
        tmp_path,
        {
            "ok": True,
            "id": "ionos",
            "weekly": 0,
            "cursor_label": "82%",
            "remaining_pct": 82,
            "running": 0,
            "queued": 0,
            "jobs": [],
        },
    )
    got = bobstat.read_peer(tmp_path, "ionos")
    assert got["account_remaining_pct"] == 82
    assert got["cursor_remaining_pct"] == 82
    # Later POINT without remaining must keep numeric remaining (not wipe via label).
    line = bobstat.format_bob_point(
        {"id": "ionos", "weekly": 0, "running": 1, "queued": 0, "lastSeen": "t", "jobs": []}
    )
    assert "remaining=" not in line or "remaining=82" in bobstat.format_bob_point(got)
    bobstat.write_peer(tmp_path, bobstat.parse_bob_point(line))
    kept = bobstat.read_peer(tmp_path, "ionos")
    assert kept["remaining_pct"] == 82
    assert kept["weekly"] == 0


def test_parse_bob_point_remaining_wire_field():
    line = (
        "BOB v1 id=ionos weekly=0 running=1 queued=1 "
        "lastSeen=2026-09-21T17:55:15Z jobs=- remaining=82"
    )
    doc = bobstat.parse_bob_point(line)
    assert doc is not None
    assert doc["remaining_pct"] == 82
    assert doc["account_remaining_pct"] == 82
    assert doc["cursor_remaining_pct"] == 82
    roundtrip = bobstat.format_bob_point(doc)
    assert "remaining=82" in roundtrip


def test_start_worker_irc_agent_utf8_py_compile_and_dry_run():
    raw = SPAWN.read_bytes()
    assert raw.count(0) == 0, "spawn helper must be UTF-8 (no NULs)"
    assert raw.startswith(b"#!/usr/bin/env python")
    py_compile.compile(str(SPAWN), doraise=True)
    proc = subprocess.run(
        [
            sys.executable,
            str(SPAWN),
            "--dry-run",
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
    assert "workers" in out and "ionos" in out and "4412" in out
