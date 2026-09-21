from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bobstat
import grok_talk
import irc_agent


def _args(home: Path, nick: str = "bob-ionos") -> argparse.Namespace:
    return argparse.Namespace(
        nick=nick,
        channel="#bobiverse",
        home=str(home),
        outbox="",
        hello="",
        announce_key=False,
        host="127.0.0.1",
        port=6697,
        realname="test",
        once=True,
        password="",
    )


def _enable_grok_talk(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENTIC_IRC_GROK_TALK", "1")
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))


def test_enqueue_when_enabled_and_fuel(tmp_path, monkeypatch):
    _enable_grok_talk(tmp_path, monkeypatch)
    bobstat.write_peer(
        tmp_path,
        {"ok": True, "id": "ionos", "weekly": 12, "running": 0, "queued": 0, "jobs": []},
    )
    dedupe: dict[tuple[str, str], float] = {}
    job = grok_talk.enqueue_mention(
        tmp_path,
        "ionos",
        "bob-ionos",
        ["bob-ionos"],
        "simon",
        "#bobiverse",
        "@bob-ionos what is the shop status?",
        to_me=False,
        to_channel=True,
        dedupe_last=dedupe,
        now=1000.0,
    )
    assert job
    rows = grok_talk.inbox_path(tmp_path).read_text(encoding="utf-8").strip().splitlines()
    assert len(rows) == 1
    doc = json.loads(rows[0])
    assert doc["asker"] == "simon"
    assert doc["machine_id"] == "ionos"
    assert doc["reply_target"] == "#bobiverse"


def test_ac2_weekly_zero_with_cursor_label_does_not_enqueue(tmp_path, monkeypatch):
    """AC2: weekly=0 must not enqueue; cursor_label is not an IRC fuel gate (#126)."""
    _enable_grok_talk(tmp_path, monkeypatch)
    bobstat.write_peer(
        tmp_path,
        {
            "ok": True,
            "id": "ionos",
            "weekly": 0,
            "cursor_label": "-£75",
            "running": 0,
            "queued": 0,
            "jobs": [],
        },
    )
    dedupe: dict[tuple[str, str], float] = {}
    assert (
        grok_talk.enqueue_mention(
            tmp_path,
            "ionos",
            "bob-ionos",
            ["bob-ionos"],
            "simon",
            "#bobiverse",
            "@bob-ionos ping",
            to_me=False,
            to_channel=True,
            dedupe_last=dedupe,
        )
        is None
    )
    assert not grok_talk.inbox_path(tmp_path).exists()


def test_no_enqueue_when_weekly_zero(tmp_path, monkeypatch):
    _enable_grok_talk(tmp_path, monkeypatch)
    bobstat.write_peer(
        tmp_path,
        {"ok": True, "id": "ionos", "weekly": 0, "running": 0, "queued": 0, "jobs": []},
    )
    dedupe: dict[tuple[str, str], float] = {}
    assert (
        grok_talk.enqueue_mention(
            tmp_path,
            "ionos",
            "bob-ionos",
            ["bob-ionos"],
            "simon",
            "#bobiverse",
            "@bob-ionos ping",
            to_me=False,
            to_channel=True,
            dedupe_last=dedupe,
        )
        is None
    )
    assert not grok_talk.inbox_path(tmp_path).exists()


def test_no_enqueue_protocol_or_bob_asker(tmp_path, monkeypatch):
    _enable_grok_talk(tmp_path, monkeypatch)
    bobstat.write_peer(
        tmp_path,
        {"ok": True, "id": "ionos", "weekly": 50, "running": 0, "queued": 0, "jobs": []},
    )
    dedupe: dict[tuple[str, str], float] = {}
    assert grok_talk.enqueue_mention(
        tmp_path, "ionos", "bob-ionos", ["bob-ionos"], "simon", "#bobiverse", "!bobiverse", False, True, dedupe
    ) is None
    assert grok_talk.enqueue_mention(
        tmp_path,
        "ionos",
        "bob-ionos",
        ["bob-ionos"],
        "bob-flamingo",
        "#bobiverse",
        "@bob-ionos hi",
        False,
        True,
        dedupe,
    ) is None


def test_drain_writes_privmsg_to_outbox(tmp_path):
    comp = grok_talk.completion_path(tmp_path)
    comp.write_text(
        json.dumps(
            {
                "v": 1,
                "job_id": "abc",
                "reply_target": "#bobiverse",
                "lines": ["@simon LLM says the worker is idle."],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "outbox.txt"
    lines = grok_talk.drain_completions_to_outbox(tmp_path, outbox=out)
    assert lines == ["PRIVMSG #bobiverse :@simon LLM says the worker is idle."]
    assert out.read_text(encoding="utf-8").strip() == lines[0]


def test_agent_mention_enqueues_and_drains_llm_reply(tmp_path, monkeypatch):
    _enable_grok_talk(tmp_path, monkeypatch)
    bobstat.write_peer(
        tmp_path,
        {"ok": True, "id": "ionos", "weekly": 8, "running": 0, "queued": 0, "jobs": []},
    )
    sent: list[str] = []

    def _send(self, line: str) -> None:
        sent.append(line)

    monkeypatch.setattr(irc_agent.Client, "send", _send)
    monkeypatch.setattr(irc_agent.time, "sleep", lambda *_a, **_k: None)
    c = irc_agent.Client(_args(tmp_path))
    c.channels = ["#bobiverse", "#ionos"]
    c.chan = "#bobiverse"
    c.sock = object()  # drain_outbox_once gate
    c.handle_privmsg("simon!u@h", "#bobiverse", "@bob-ionos brief status?")

    assert grok_talk.inbox_path(tmp_path).is_file()
    job = json.loads(grok_talk.inbox_path(tmp_path).read_text(encoding="utf-8").strip())
    grok_talk.completion_path(tmp_path).write_text(
        json.dumps(
            {
                "v": 1,
                "job_id": job["job_id"],
                "reply_target": "#bobiverse",
                "lines": ["@simon ionos: MRB queue is empty on this seat."],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    drained = c.drain_outbox_once()
    assert any("MRB queue is empty" in x for x in drained)
    assert any("MRB queue is empty" in x for x in sent)
    acks = [x for x in sent if "ionos here" in x]
    assert acks


def test_grok_disabled_matches_ack_only_no_inbox(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    bobstat.write_peer(
        tmp_path,
        {"ok": True, "id": "ionos", "weekly": 0, "running": 0, "queued": 0, "jobs": []},
    )
    sent: list[str] = []

    def _send(self, line: str) -> None:
        sent.append(line)

    monkeypatch.setattr(irc_agent.Client, "send", _send)
    c = irc_agent.Client(_args(tmp_path))
    c.channels = ["#bobiverse"]
    c.chan = "#bobiverse"
    c.handle_privmsg("cursor-flamingo!u@h", "#bobiverse", "@bob-ionos hello?")
    assert sent
    assert not grok_talk.inbox_path(tmp_path).exists()
