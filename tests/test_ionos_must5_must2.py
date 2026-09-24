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
from ionos_peer_live import apply_point_remaining, write_live_watch_peer

ROOT = Path(__file__).resolve().parents[1]
FIX = Path(__file__).resolve().parent / "fixtures"
SPAWN = ROOT / "scripts" / "start_worker_irc_agent.py"
USAGE_FIX = FIX / "cursor-usage-82pct.json"
LIVE_FIX = FIX / "ionos-peer-live-2026-09-21.json"
FLAMINGO_WATCH = FIX / "flamingo-peer-watch-2026-09-21.json"


def numeric_missing(peer: dict) -> bool:
    for key in bobstat.REMAINING_KEYS:
        if peer.get(key) not in (None, ""):
            return False
    return True


def apply_point_remaining_on_peer(home: Path, machine_id: str, doc: dict, remaining: int) -> dict:
    """Ingest BOB v1 POINT remaining= onto a Watch-shaped peer (not author remaining_* JSON)."""
    bobstat.write_peer(home, doc)
    point = (
        f"BOB v1 id={machine_id} weekly=0 running={int(doc['running'])} "
        f"queued={int(doc['queued'])} lastSeen={doc['lastSeen']} jobs=- "
        f"remaining={remaining}"
    )
    parsed = bobstat.parse_bob_point(point)
    if not parsed:
        raise AssertionError("parse_bob_point failed")
    bobstat.write_peer(home, parsed)
    peer = bobstat.read_peer(home, machine_id)
    assert peer is not None
    return peer


def test_live_ionos_peer_no_remaining_until_point_or_usage(tmp_path):
    """Live Watch shape (no remaining_*): fuel stays off until POINT or usage refresh."""
    doc = write_live_watch_peer(tmp_path)
    got = bobstat.read_peer(tmp_path, "ionos")
    assert got["weekly"] == 0
    assert got.get("cursor_label") == doc.get("cursor_label")
    assert numeric_missing(got)
    assert grok_talk.fuel_ok(tmp_path, "ionos") is False
    line = bobtalk.mention_reply_line(
        tmp_path, "ionos", ["bob-ionos"], "simon", "@bob-ionos status?"
    )
    assert line is not None
    assert "cannot grok-talk" in line


def test_live_ionos_peer_fuel_ok_after_point_remaining_ingest(tmp_path):
    """BOB v1 POINT remaining= on live ionos peer → bob-peers fuel + ACK (MUST 5)."""
    peer = apply_point_remaining(tmp_path, 82)
    assert peer["remaining_pct"] == 82
    assert grok_talk.fuel_ok(tmp_path, "ionos") is True
    line = bobtalk.mention_reply_line(
        tmp_path, "ionos", ["bob-ionos"], "simon", "@bob-ionos status?"
    )
    assert line is not None
    assert "cannot grok-talk" not in line
    assert "weekly=0 (cursor remaining=82%)" in line


def test_watch_flamingo_peer_fuel_ok_after_point_remaining_ingest(tmp_path):
    """Watch-shaped flamingo.json (no remaining_* keys) → fuel only after POINT remaining=."""
    doc = json.loads(FLAMINGO_WATCH.read_text(encoding="utf-8"))
    got_before = bobstat.read_peer(tmp_path, "flamingo")
    assert got_before is None
    bobstat.write_peer(tmp_path, doc)
    got = bobstat.read_peer(tmp_path, "flamingo")
    assert numeric_missing(got)
    assert grok_talk.fuel_ok(tmp_path, "flamingo") is False

    peer = apply_point_remaining_on_peer(tmp_path, "flamingo", doc, 82)
    assert peer["remaining_pct"] == 82
    on_disk = json.loads((tmp_path / "bob-peers" / "flamingo.json").read_text(encoding="utf-8"))
    assert on_disk.get("lastSeen") == doc["lastSeen"]
    assert grok_talk.fuel_ok(tmp_path, "flamingo") is True
    line = bobtalk.mention_reply_line(
        tmp_path, "flamingo", ["bob-flamingo"], "simon", "@bob-flamingo status?"
    )
    assert line is not None
    assert "cannot grok-talk" not in line


def test_live_ionos_peer_grok_talk_enqueue_after_point(tmp_path, monkeypatch):
    """Replay bob-peers/ionos.json after POINT: inbox when grok-talk enabled (MUST 5)."""
    (tmp_path / "grok-talk.json").write_text('{"grok_talk_enabled": true}\n', encoding="utf-8")
    apply_point_remaining(tmp_path, 82)
    peer_path = tmp_path / "bob-peers" / "ionos.json"
    assert peer_path.is_file()
    on_disk = json.loads(peer_path.read_text(encoding="utf-8"))
    assert on_disk.get("remaining_pct") == 82
    assert grok_talk.fuel_ok(tmp_path, "ionos") is True
    dedupe: dict[tuple[str, str], float] = {}
    job = grok_talk.enqueue_mention(
        tmp_path,
        "ionos",
        "bob-ionos",
        ["bob-ionos"],
        "simon",
        "#ionos",
        "@bob-ionos status?",
        to_me=False,
        to_channel=True,
        dedupe_last=dedupe,
        now=2000.0,
    )
    assert job
    assert grok_talk.inbox_path(tmp_path).is_file()


def test_live_ionos_peer_fuel_ok_after_cursor_usage_refresh(tmp_path):
    """Watch file + Get-CursorAgentUsage-shaped doc (not cursor_label) → fuel."""
    write_live_watch_peer(tmp_path)
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
        bobstat.parse_bob_point(
            "BOB v1 id=ionos weekly=0 running=0 queued=0 lastSeen=t jobs=- remaining=82"
        ),
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


def test_cursor_label_alone_is_not_fuel(tmp_path):
    write_live_watch_peer(tmp_path)
    got = bobstat.read_peer(tmp_path, "ionos")
    assert got.get("cursor_label") == "82%"
    assert numeric_missing(got)
    assert grok_talk.fuel_ok(tmp_path, "ionos") is False


def test_live_ionos_peer_replay_after_point_or_usage_refresh(tmp_path):
    """Replay Watch-shaped ionos.json (live keys) → fuel only via POINT or usage merge."""
    fixture = json.loads(LIVE_FIX.read_text(encoding="utf-8"))
    bobstat.write_peer(tmp_path, fixture)
    got = bobstat.read_peer(tmp_path, "ionos")
    assert got is not None
    assert numeric_missing(got)
    assert grok_talk.fuel_ok(tmp_path, "ionos") is False

    usage = json.loads(USAGE_FIX.read_text(encoding="utf-8"))
    assert bobstat.refresh_peer_cursor_remaining(tmp_path, "ionos", usage_doc=usage)
    on_disk = json.loads((tmp_path / "bob-peers" / "ionos.json").read_text(encoding="utf-8"))
    assert on_disk.get("remaining_pct") == 82
    assert grok_talk.fuel_ok(tmp_path, "ionos") is True
    line = bobtalk.mention_reply_line(
        tmp_path, "ionos", ["bob-ionos"], "simon", "@bob-ionos status?"
    )
    assert line is not None
    assert "cannot grok-talk" not in line


def test_point_cur_label_does_not_fuel_usage_refresh_does(tmp_path):
    """Sister POINT with cur= only (no remaining=) stays non-fuel until usage refresh."""
    write_live_watch_peer(tmp_path)
    point = (
        "BOB v1 id=ionos weekly=0 running=1 queued=1 "
        "lastSeen=2026-09-21T17:55:15Z jobs=- cur=82%"
    )
    doc = bobstat.parse_bob_point(point)
    assert doc is not None
    bobstat.write_peer(tmp_path, doc)
    got = bobstat.read_peer(tmp_path, "ionos")
    assert got.get("cursor_label") == "82%"
    assert numeric_missing(got)
    assert grok_talk.fuel_ok(tmp_path, "ionos") is False
    usage = json.loads(USAGE_FIX.read_text(encoding="utf-8"))
    assert bobstat.refresh_peer_cursor_remaining(tmp_path, "ionos", usage_doc=usage)
    assert grok_talk.fuel_ok(tmp_path, "ionos") is True


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
    cleaned = MagicMock()
    cleaned.scanned = True
    with (
        patch.object(start_worker_irc_agent.subprocess, "Popen", popen),
        patch.object(start_worker_irc_agent.prior_irc, "clean_priors", return_value=cleaned),
    ):
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
