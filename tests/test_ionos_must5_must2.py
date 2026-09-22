from __future__ import annotations

import json
import py_compile
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bobstat
import bobtalk
import grok_talk
import start_worker_irc_agent

ROOT = Path(__file__).resolve().parents[1]
FIX = Path(__file__).resolve().parent / "fixtures"
SPAWN = ROOT / "scripts" / "start_worker_irc_agent.py"
LIVE = FIX / "ionos-peer-live-2026-09-21.json"
USAGE_FIX = FIX / "cursor-usage-82pct.json"


def _write_live_peer(tmp_path: Path) -> dict:
    doc = json.loads(LIVE.read_text(encoding="utf-8"))
    bobstat.write_peer(tmp_path, doc)
    return doc


def test_live_ionos_peer_no_remaining_until_point_or_usage(tmp_path):
    """Live Watch shape (no remaining_*): fuel stays off until POINT or usage refresh."""
    doc = _write_live_peer(tmp_path)
    got = bobstat.read_peer(tmp_path, "ionos")
    assert got["weekly"] == 0
    assert got.get("cursor_label") == "82%"
    assert numeric_missing(got)
    assert grok_talk.fuel_ok(tmp_path, "ionos") is False
    line = bobtalk.mention_reply_line(
        tmp_path, "ionos", ["bob-ionos"], "simon", "@bob-ionos status?"
    )
    assert line is not None
    assert "cannot grok-talk" in line


def numeric_missing(peer: dict) -> bool:
    for key in bobstat.REMAINING_KEYS:
        if peer.get(key) not in (None, ""):
            return False
    return True


def test_live_ionos_peer_fuel_ok_after_point_remaining_ingest(tmp_path):
    """BOB v1 POINT remaining= on live ionos peer → bob-peers fuel + ACK (MUST 5)."""
    doc = _write_live_peer(tmp_path)
    point = (
        f"BOB v1 id=ionos weekly=0 running={int(doc['running'])} queued={int(doc['queued'])} "
        f"lastSeen={doc['lastSeen']} jobs=- remaining=82"
    )
    parsed = bobstat.parse_bob_point(point)
    assert parsed is not None
    bobstat.write_peer(tmp_path, parsed)
    got = bobstat.read_peer(tmp_path, "ionos")
    assert got["remaining_pct"] == 82
    assert grok_talk.fuel_ok(tmp_path, "ionos") is True
    line = bobtalk.mention_reply_line(
        tmp_path, "ionos", ["bob-ionos"], "simon", "@bob-ionos status?"
    )
    assert line is not None
    assert "cannot grok-talk" not in line
    assert "weekly=0 (cursor remaining=82%)" in line


def test_live_ionos_peer_fuel_ok_after_cursor_usage_refresh(tmp_path):
    """Watch file + Get-CursorAgentUsage-shaped doc (not cursor_label) → fuel."""
    _write_live_peer(tmp_path)
    usage = json.loads(USAGE_FIX.read_text(encoding="utf-8"))
    assert bobstat.refresh_peer_cursor_remaining(tmp_path, "ionos", usage_doc=usage)
    got = bobstat.read_peer(tmp_path, "ionos")
    assert got["remaining_pct"] == 82
    assert grok_talk.fuel_ok(tmp_path, "ionos") is True
    line = bobtalk.mention_reply_line(
        tmp_path, "ionos", ["bob-ionos"], "simon", "@bob-ionos status?"
    )
    assert line is not None
    assert "cannot grok-talk" not in line


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
    line = bobstat.format_bob_point(got)
    assert "remaining=82" in line
    bobstat.write_peer(
        tmp_path,
        bobstat.parse_bob_point(
            "BOB v1 id=ionos weekly=0 running=1 queued=0 lastSeen=t jobs=-"
        ),
    )
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


def test_start_worker_irc_agent_utf8_py_compile_and_dry_run(tmp_path):
    raw = SPAWN.read_bytes()
    assert raw.count(0) == 0, "spawn helper must be UTF-8 (no NULs)"
    assert raw.startswith(b"#!/usr/bin/env python")
    py_compile.compile(str(SPAWN), doraise=True)
    workers = tmp_path / "workers" / "ionos" / "4412"
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
    assert "workers" in out and "ionos" in out and "4412" in out
    assert not workers.exists(), "dry-run must not create worker home"


def test_start_worker_irc_agent_spawns_irc_agent(tmp_path):
    popen = MagicMock(return_value=MagicMock(pid=4412))
    with patch.object(start_worker_irc_agent.subprocess, "Popen", popen):
        rc = start_worker_irc_agent.main(
            [
                "--fleet-home",
                str(tmp_path),
                "--machine-id",
                "ionos",
                "--pid",
                "4412",
            ]
        )
    assert rc == 0
    popen.assert_called_once()
    cmd = popen.call_args[0][0]
    assert "irc_agent.py" in cmd[2]
    assert "w-io-4412" in cmd
    home = tmp_path / "workers" / "ionos" / "4412"
    assert home.is_dir()
