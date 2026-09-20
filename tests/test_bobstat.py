from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bobstat
import moot
import wire


def test_roundtrip_idle():
    line = bobstat.format_bob_point(
        {
            "id": "flamingo",
            "weekly": 96,
            "running": 0,
            "queued": 0,
            "lastSeen": "2026-09-20T08:31:16Z",
            "jobs": [],
        }
    )
    assert line.startswith("BOB v1 id=flamingo")
    assert "jobs=-" in line
    doc = bobstat.parse_bob_point(line)
    assert doc["id"] == "flamingo"
    assert doc["weekly"] == 96
    assert doc["running"] == 0
    assert doc["jobs"] == []


def test_jobs_and_reject_garbage():
    line = bobstat.format_bob_point(
        {
            "id": "ionos",
            "weekly": 4,
            "running": 1,
            "queued": 1,
            "lastSeen": "2026-09-20T08:00:00Z",
            "jobs": [
                {"repo": "SimonBarnett/agentic_build", "state": "running"},
                {"repo": "SimonBarnett/FormPrep", "state": "queued"},
            ],
        }
    )
    doc = bobstat.parse_bob_point(line)
    assert doc["running"] == 1
    repos = [j["repo"] for j in doc["jobs"]]
    assert "SimonBarnett/agentic_build" in repos
    assert bobstat.parse_bob_point("hello") is None
    assert bobstat.parse_bob_point("BOB v1 id=NOPE weekly=1 running=0 queued=0 lastSeen=- jobs=-") is None


def test_point_on_free_moot_writes_peer(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    mid = "b0b1be15e0000001"
    st = moot.apply_moot({}, "bob-flamingo", wire.parse_moot_line(f"MOOT v1 OPEN {mid} bob-flamingo free :bobiverse"), tmp_path)
    st = moot.apply_moot(st, "bob-ionos", wire.parse_moot_line(f"MOOT v1 JOIN {mid}"), tmp_path)
    text = bobstat.format_bob_point({"id": "ionos", "weekly": 9, "running": 0, "queued": 0, "lastSeen": "2026-09-20T09:00:00Z", "jobs": []})
    st = moot.apply_moot(st, "bob-ionos", wire.parse_moot_line(f"MOOT v1 POINT {mid} :{text}"), tmp_path)
    assert st["state"] == "open"
    assert "bob-ionos" in [x.lower() for x in st["roster"]] or "bob-ionos" in st["roster"]
    doc = bobstat.parse_bob_point(text)
    bobstat.write_peer(tmp_path, doc)
    got = bobstat.read_peer(tmp_path, "ionos")
    assert got["weekly"] == 9
    assert got["source"] == "irc"
