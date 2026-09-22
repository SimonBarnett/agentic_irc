"""Live ionos bob-peers shape captured from Watch (no remaining_* keys)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bobstat  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "ionos-peer-live-2026-09-21.json"


def write_live_watch_peer(home: Path) -> dict:
    doc = json.loads(FIX.read_text(encoding="utf-8"))
    bobstat.write_peer(home, doc)
    return doc


def apply_point_remaining(home: Path, remaining: int = 82) -> dict:
    doc = write_live_watch_peer(home)
    point = (
        f"BOB v1 id=ionos weekly=0 running={int(doc['running'])} "
        f"queued={int(doc['queued'])} lastSeen={doc['lastSeen']} jobs=- "
        f"remaining={remaining}"
    )
    parsed = bobstat.parse_bob_point(point)
    if not parsed:
        raise AssertionError("parse_bob_point failed")
    bobstat.write_peer(home, parsed)
    peer = bobstat.read_peer(home, "ionos")
    assert peer is not None
    return peer
