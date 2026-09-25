"""Test-pack for issue #167 â€” rooms, webhook-only working_on, no Query status."""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import argparse

import bobreport
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


def test_talk_seat_joins_own_shop_only(tmp_path, monkeypatch):
    # CAST IRON (Simon 2026-09-25): workers/seats JOIN #{machine} only, never #bobiverse.
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    c = irc_agent.Client(_args(tmp_path, "flamingo-17568", channel="#bobiverse,#flamingo,#agentic_irc"))
    assert c.chan == "#flamingo"
    assert c.channels == ["#flamingo"]
    c.handle_join("flamingo-17568", "#flamingo")
    assert c.joined.is_set()
    assert not c._pending_joins


def test_worker_auto_parts_foreign_channel(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    c = irc_agent.Client(_args(tmp_path, "marchhare-34992", channel="#bobiverse,#marchhare"))
    sent: list[str] = []
    c.send = lambda line: sent.append(line)  # type: ignore[method-assign]
    c.handle_join("marchhare-34992", "#bobiverse")
    assert any(s.startswith("PART #bobiverse :") for s in sent)
    sent.clear()
    c.handle_join("marchhare-34992", "#marchhare")
    assert not sent
    c2 = irc_agent.Client(_args(tmp_path, "bob-marchhare", channel="#bobiverse,#marchhare"))
    s2: list[str] = []
    c2.send = lambda line: s2.append(line)  # type: ignore[method-assign]
    c2.handle_join("bob-marchhare", "#bobiverse")
    assert not any(s.startswith("PART") for s in s2)




def test_mrb_worker_auto_parts_agentic_irc_and_keeps_shop(tmp_path, monkeypatch):
    """Hostile: extras like #agentic_irc are PART'd; own shop is not."""
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    c = irc_agent.Client(_args(tmp_path, "w-mh-41124", channel="#bobiverse,#marchhare,#agentic_irc"))
    assert c.channels == ["#marchhare"]
    sent: list[str] = []
    c.send = lambda line: sent.append(line)  # type: ignore[method-assign]
    c.handle_join("w-mh-41124", "#agentic_irc")
    assert any(s.startswith("PART #agentic_irc :workers join") for s in sent)
    sent.clear()
    c.handle_join("w-mh-41124", "#marchhare")
    assert sent == []
    c.handle_join("w-mh-41124", "#flamingo")
    assert any(s.startswith("PART #flamingo :") for s in sent)


def test_start_talk_seat_refuses_steal_binding():
    src = (Path(__file__).resolve().parents[1] / "scripts" / "Start-TalkSeat.ps1").read_text(
        encoding="utf-8"
    )
    assert "talk_seat_pid.py" in src
    assert "--bind-home" in src
    assert "LASTEXITCODE -eq 3" in src

def test_mrb_w_star_and_agentic_irc_refused(tmp_path, monkeypatch):
    """MRB #209: w-* and talk seats never allowed on #bobiverse/#agentic_irc."""
    assert bobreport.channels_for_nick("w-mh-41124", "#bobiverse,#marchhare") == ["#marchhare"]
    assert not bobreport.worker_channel_allowed("w-io-1", "#agentic_irc")
    assert bobreport.worker_channel_allowed("w-io-1", "#ionos")
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    c = irc_agent.Client(_args(tmp_path, "w-mh-99", channel="#bobiverse,#marchhare"))
    assert c.channels == ["#marchhare"]
    sent: list[str] = []
    c.send = lambda line: sent.append(line)  # type: ignore[method-assign]
    c.handle_join("w-mh-99", "#bobiverse")
    assert any(s.startswith("PART #bobiverse :") for s in sent)
    assert any("workers join" in s for s in sent)


def test_mrb_underscore_suffix_still_shop_only():
    # live_nick may gain _l on collision; original_nick drives allow
    assert bobreport.worker_channel_allowed("marchhare-34992", "#marchhare")
    assert not bobreport.worker_channel_allowed("marchhare-34992_", "#bobiverse")
