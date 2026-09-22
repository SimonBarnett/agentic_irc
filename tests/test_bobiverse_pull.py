from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bobreport
import bobstat
import bobtalk
import irc_agent


def test_should_periodic_bobiverse_pull():
    assert bobreport.should_periodic_bobiverse_pull("bob-ionos")
    assert not bobreport.should_periodic_bobiverse_pull("bob-ionos", chair=True)
    assert not bobreport.should_periodic_bobiverse_pull("flamingo-17568")
    assert not bobreport.should_periodic_bobiverse_pull("w-io-4412")
    assert not bobreport.should_periodic_bobiverse_pull("Jeeves")


def test_digest_whisper_assembler_single_line():
    asm = bobreport.DigestWhisperAssembler()
    doc = {"v": 1, "machines": {}}
    assert asm.feed("Jeeves", json.dumps(doc)) == doc


def test_digest_whisper_assembler_chunks():
    asm = bobreport.DigestWhisperAssembler()
    raw = json.dumps({"v": 1, "machines": {"ionos": {"id": "ionos"}}}, separators=(",", ":"))
    chunks = bobreport._chunk_json(raw)
    assert len(chunks) >= 1
    out = None
    for c in chunks:
        out = asm.feed("Jeeves", c)
    assert out is not None
    assert out["machines"]["ionos"]["id"] == "ionos"


def test_merge_payload_skips_lastseen_only(tmp_path):
    bobstat.write_peer(
        tmp_path,
        {
            "ok": True,
            "id": "ionos",
            "weekly": 55,
            "lastSeen": "2026-09-22T10:00:00Z",
            "running": 0,
            "queued": 0,
        },
    )
    chair = {
        "id": "ionos",
        "weekly": 55,
        "lastSeen": "2026-09-22T09:00:00Z",
        "running": 0,
        "queued": 0,
    }
    assert bobreport.merge_payload_local_peer_ahead_of_chair(tmp_path, "ionos", chair) is None


def test_merge_payload_weekly_delta(tmp_path):
    bobstat.write_peer(tmp_path, {"ok": True, "id": "ionos", "weekly": 61, "running": 0, "queued": 0})
    chair = {"id": "ionos", "weekly": 50, "running": 0, "queued": 0}
    payload = bobreport.merge_payload_local_peer_ahead_of_chair(tmp_path, "ionos", chair)
    assert payload == {"op": "merge", "machine": "ionos", "weekly": 61}


def test_ingest_fleet_digest_pull_writes_peer(tmp_path):
    pull = {
        "v": 1,
        "machines": {
            "flamingo": {
                "id": "flamingo",
                "weekly": 88,
                "running": 1,
                "queued": 0,
                "online": True,
            }
        },
    }
    bobreport.ingest_fleet_digest_pull(tmp_path, pull)
    peer = bobstat.read_peer(tmp_path, "flamingo")
    assert peer and peer.get("weekly") == 88
    doc = bobreport.load_digest(tmp_path)
    assert doc["machines"]["flamingo"]["weekly"] == 88


def _args(home: Path, nick: str = "bob-ionos") -> argparse.Namespace:
    return argparse.Namespace(
        nick=nick,
        channel="#bobiverse,#ionos",
        home=str(home),
        outbox="",
        hello="",
        announce_key=False,
        host="127.0.0.1",
        port=6697,
        realname="test",
        once=True,
        password="",
        chair=False,
    )


def test_bobiverse_pull_sends_command(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    sent: list[str] = []

    def _send(self, line: str) -> None:
        sent.append(line)

    monkeypatch.setattr(irc_agent.Client, "send", _send)
    monkeypatch.setattr(irc_agent.time, "sleep", lambda *_a, **_k: None)
    c = irc_agent.Client(_args(tmp_path))
    c.joined.set()
    c.channels = ["#bobiverse", "#ionos"]
    c._bobiverse_pull_last = 0.0
    c._maybe_bobiverse_pull()
    assert sent == ["PRIVMSG #bobiverse :!bobiverse"]


def test_talk_seat_does_not_pull(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    sent: list[str] = []

    def _send(self, line: str) -> None:
        sent.append(line)

    monkeypatch.setattr(irc_agent.Client, "send", _send)
    monkeypatch.setattr(irc_agent.time, "sleep", lambda *_a, **_k: None)
    c = irc_agent.Client(_args(tmp_path, nick="flamingo-17568"))
    c.joined.set()
    c._maybe_bobiverse_pull()
    assert sent == []


def test_digest_whisper_posts_webhook(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    monkeypatch.setenv("AGENTIC_IRC_CHAIR_NICK", "Jeeves")
    monkeypatch.setattr("protect.protect_path", lambda *_a, **_k: None)
    bobstat.write_peer(tmp_path, {"ok": True, "id": "ionos", "weekly": 77, "running": 0, "queued": 0})
    posted: list[dict] = []

    def _post(payload: dict) -> int:
        posted.append(payload)
        return 204

    monkeypatch.setattr("post_working_on.post", _post)
    c = irc_agent.Client(_args(tmp_path, nick="bob-ionos"))
    pull = {
        "v": 1,
        "machines": {
            "ionos": {"id": "ionos", "weekly": 40, "running": 0, "queued": 0},
            "flamingo": {"id": "flamingo", "weekly": 10, "running": 0, "queued": 0},
        },
    }
    raw = json.dumps(pull, separators=(",", ":"), sort_keys=True)
    for line in bobreport._chunk_json(raw):
        c.handle_privmsg("Jeeves!u@h", "bob-ionos", line)
    assert posted == [{"op": "merge", "machine": "ionos", "weekly": 77}]
    peer = bobstat.read_peer(tmp_path, "flamingo")
    assert peer and peer.get("weekly") == 10
