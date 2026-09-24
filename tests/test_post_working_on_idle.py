"""Offline tests for post_working_on --idle webhook + shop sequence (issue #105)."""
from __future__ import annotations

import sys

import bobreport
import post_working_on as pwo


def test_idle_merge_sequence_state_idle(tmp_path):
    digest_home = tmp_path
    mid, pid, nick, kind = "flamingo", 4412, "w-fl-4412", "cursor"
    desc = "agentic_irc shop idle gate"

    bobreport.apply_callback(
        digest_home,
        {
            "op": "merge",
            "machine": mid,
            "pid": pid,
            "nick": nick,
            "kind": kind,
            "state": "running",
            "online": True,
            "working_on": "old job",
        },
    )

    def apply_post(payload: dict) -> int:
        out = bobreport.apply_callback(digest_home, payload)
        assert out.ok
        return 200

    marked = pwo.base_payload(mid, pid, nick, kind, "running")
    marked["working_on"] = desc
    apply_post(marked)
    idle = pwo.base_payload(mid, pid, nick, kind, "idle")
    assert "working_on" not in idle
    apply_post(idle)

    doc = bobreport.load_digest(digest_home)
    assert doc["machines"]["flamingo"]["workers"]["4412"]["state"] == "idle"


def test_main_idle_posts_idle_without_working_on_key(tmp_path, monkeypatch):
    digest_home = tmp_path
    mid, pid, nick = "flamingo", 4412, "w-fl-4412"
    desc = "finishing shop FR"

    bobreport.apply_callback(
        digest_home,
        {
            "op": "merge",
            "machine": mid,
            "pid": pid,
            "nick": nick,
            "kind": "cursor",
            "state": "running",
            "online": True,
            "working_on": "prior",
        },
    )

    posted: list[dict] = []

    def fake_post(payload: dict) -> int:
        posted.append(dict(payload))
        bobreport.apply_callback(digest_home, payload)
        return 200

    monkeypatch.setattr(pwo, "post", fake_post)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "post_working_on.py",
            "--machine",
            mid,
            "--pid",
            str(pid),
            "--nick",
            nick,
            "--idle",
            "--working-on",
            desc,
        ],
    )

    assert pwo.main() == 0
    idle_posts = [p for p in posted if p.get("state") == "idle"]
    assert len(idle_posts) == 1
    assert "working_on" not in idle_posts[0]
    assert bobreport.load_digest(digest_home)["machines"]["flamingo"]["workers"]["4412"]["state"] == "idle"
    outbox = tmp_path / "outbox.txt"
    assert not outbox.exists()
