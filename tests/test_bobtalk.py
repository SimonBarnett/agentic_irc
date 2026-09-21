from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bobstat
import bobtalk


def test_idle_one_line(tmp_path):
    bobstat.write_peer(
        tmp_path,
        {
            "ok": True,
            "id": "flamingo",
            "weekly": 90,
            "running": 0,
            "queued": 0,
            "lastSeen": "2026-09-20T08:00:00Z",
            "jobs": [],
        },
    )
    lines = bobtalk.network_talk_lines(tmp_path)
    assert lines == ["flamingo is idle."]


def test_busy_facts_split(tmp_path):
    bobstat.write_peer(
        tmp_path,
        {
            "ok": True,
            "id": "ionos",
            "weekly": 4,
            "running": 1,
            "queued": 0,
            "model": "Cursor Models",
            "kind": "mrb",
            "repo": "SimonBarnett/agentic_build",
            "sha": "82a8fb2deadbeef",
            "duration": "12 minutes",
            "responding": True,
            "jobs": [{"repo": "SimonBarnett/agentic_build", "state": "running"}],
        },
    )
    lines = bobtalk.peer_talk_lines(bobstat.read_peer(tmp_path, "ionos"))
    assert lines[0] == "ionos is on Cursor Models now."
    assert "MRB of SimonBarnett/agentic_build" in lines[1]
    assert any(l.startswith("SHA is 82a8fb") for l in lines)
    assert any("still responding" in l for l in lines)


def test_briefer_chair_else_first_bob():
    st = {"chair": "simon", "roster": ["simon", "bob-ionos", "bob-flamingo"]}
    assert bobtalk.briefer_nick(st) == "bob-ionos"
    assert bobtalk.is_briefer(st, "bob-ionos")
    assert not bobtalk.is_briefer(st, "bob-flamingo")

    st2 = {"chair": "bob-flamingo", "roster": ["bob-flamingo", "bob-ionos"]}
    assert bobtalk.is_briefer(st2, "bob-flamingo")


def test_ionos_repo_question_mark_from_job(tmp_path):
    bobstat.write_peer(
        tmp_path,
        {
            "ok": True,
            "id": "ionos",
            "running": 1,
            "queued": 0,
            "repo": "?",
            "jobs": [{"repo": "SimonBarnett/agentic_irc", "state": "running"}],
        },
    )
    peer = bobstat.read_peer(tmp_path, "ionos")
    lines = bobtalk.peer_talk_lines(peer)
    assert not any("Working on ?" in l for l in lines)
    assert any("SimonBarnett/agentic_irc" in l for l in lines)
    tray = bobtalk.format_tray_peer_line(peer)
    assert "repo=SimonBarnett/agentic_irc" in tray


def test_tray_pull_lines_order(tmp_path):
    bobstat.write_peer(tmp_path, {"ok": True, "id": "flamingo", "running": 0, "queued": 0, "jobs": []})
    bobstat.write_peer(tmp_path, {"ok": True, "id": "ionos", "running": 0, "queued": 0, "jobs": []})
    lines = bobtalk.tray_pull_lines(tmp_path)
    assert len(lines) >= 2
    assert all(l.startswith(bobtalk.TRAY_PREFIX) for l in lines)


def test_change_ignores_last_seen_only():
    before = {
        "id": "ionos",
        "running": 1,
        "queued": 0,
        "kind": "mrb",
        "repo": "SimonBarnett/agentic_build",
        "model": "Cursor Models",
        "jobs": [{"repo": "SimonBarnett/agentic_build", "state": "running"}],
    }
    after = dict(before)
    after["lastSeen"] = "2026-09-20T09:01:00Z"
    assert bobtalk.change_talk_line(before, after) is None


def test_addressed_at_nick_and_moot_say():
    nicks = ["bob-ionos"]
    assert bobtalk.addressed_to("@bob-ionos are you up?", nicks)
    assert bobtalk.addressed_to("bob-ionos: shop brief?", nicks)
    assert bobtalk.addressed_to("MOOT v1 SAY b0b1be15e0000001 1 :@bob-ionos align shop", nicks)
    assert bobtalk.addressed_to("@all pull origin/main", nicks)
    assert not bobtalk.addressed_to("flamingo is idle.", nicks)
    assert not bobtalk.addressed_to("MOOT v1 POINT b0b1be15e0000001 :BOB v1 id=ionos", nicks)


def test_protocol_lines_skipped():
    assert bobtalk.is_protocol_line("MOOT v1 POINT b0b1be15e0000001 :x")
    assert bobtalk.is_protocol_line("AGPK v1 abc")
    assert bobtalk.is_protocol_line("!bobiverse")
    assert not bobtalk.is_protocol_line("MOOT v1 SAY b0b1be15e0000001 1 :@bob-ionos hi")
    assert not bobtalk.is_protocol_line("@bob-ionos hi")


def test_no_reply_to_other_bob(tmp_path):
    bobstat.write_peer(tmp_path, {"ok": True, "id": "ionos", "weekly": 0, "running": 0, "queued": 0, "jobs": []})
    line = bobtalk.mention_reply_line(
        tmp_path, "ionos", ["bob-ionos"], "bob-flamingo", "@bob-ionos hi"
    )
    assert line is None


def test_mention_ack_when_weekly_zero(tmp_path):
    bobstat.write_peer(
        tmp_path,
        {"ok": True, "id": "ionos", "weekly": 0, "running": 0, "queued": 0, "jobs": []},
    )
    line = bobtalk.mention_reply_line(
        tmp_path, "ionos", ["bob-ionos"], "cursor-flamingo", "@bob-ionos align shop-channel?"
    )
    assert line is not None
    assert line.startswith("@cursor-flamingo ionos here.")
    assert "weekly=0 (cannot grok-talk)" in line
    assert "idle" in line
    assert "Heard:" in line
    assert "align shop-channel" in line


def test_query_counts_as_addressed(tmp_path):
    bobstat.write_peer(
        tmp_path,
        {"ok": True, "id": "flamingo", "weekly": 8, "running": 0, "queued": 0, "jobs": []},
    )
    line = bobtalk.mention_reply_line(
        tmp_path, "flamingo", ["bob-flamingo"], "simon", "you there?", to_me=True
    )
    assert line is not None
    assert "weekly=8" in line
    assert "@simon flamingo here." in line
