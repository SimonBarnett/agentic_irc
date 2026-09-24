"""Test-pack for issue #167 — rooms, webhook-only working_on, no Query status."""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import argparse

import irc_agent
import post_working_on as pwo


def _args(home: Path, nick: str, channel: str) -> argparse.Namespace:
    return argparse.Namespace(
        nick=nick,
        channel=channel,
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


def test_agentic_irc_skill_no_query_working_on():
    skill = (
        Path(__file__).resolve().parents[1] / ".grok" / "skills" / "agentic-irc" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "PRIVMSG simon :This is what I'm working on" not in skill
    assert "webhook only" in skill.lower() or "webhook-only" in skill.lower()


def test_post_working_on_enqueue_shop_is_noop(tmp_path):
    pwo.enqueue_shop_working_on("flamingo", "w-fl-4412", "job", home=str(tmp_path))
    assert not (tmp_path / "outbox.txt").exists()


def test_talk_seat_dual_channel_shop_when_fleet_first(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    c = irc_agent.Client(_args(tmp_path, "flamingo-17568", channel="#bobiverse,#flamingo"))
    assert c.chan == "#bobiverse"
    assert c.channels == ["#bobiverse", "#flamingo"]
    c.handle_join("flamingo-17568", "#bobiverse")
    assert not c.joined.is_set()
    assert "#flamingo" in c._pending_joins
    c.handle_join("flamingo-17568", "#flamingo")
    assert c.joined.is_set()
    assert not c._pending_joins


def test_start_talk_seat_refuses_steal_binding():
    src = (Path(__file__).resolve().parents[1] / "scripts" / "Start-TalkSeat.ps1").read_text(
        encoding="utf-8"
    )
    assert "talk_seat_pid.py" in src
    assert "--bind-home" in src
    assert "LASTEXITCODE -eq 3" in src
