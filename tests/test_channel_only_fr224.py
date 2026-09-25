"""FR #224: worker output channel-only; never PRIVMSG a nick.

Failing-before-fix contract: any worker PRIVMSG to bob-*/simon/Jeeves fails.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import channel_only
import gitclaim
import irc_agent


def _args(home: Path, nick: str, channel: str, *, chair: bool = False) -> argparse.Namespace:
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
        chair=chair,
    )


def test_channel_only_worker_nicks():
    assert channel_only.is_channel_only_worker_nick("flamingo-46804")
    assert channel_only.is_channel_only_worker_nick("marchhare-34992")
    assert channel_only.is_channel_only_worker_nick("w-mh-123")
    assert not channel_only.is_channel_only_worker_nick("bob-flamingo")
    assert not channel_only.is_channel_only_worker_nick("Jeeves")
    assert not channel_only.is_channel_only_worker_nick("simon")


def test_rewrite_nick_privmsg_to_shop():
    line = "PRIVMSG bob-marchhare :pong"
    out = channel_only.rewrite_worker_outbound_line("marchhare-39768", line)
    assert out.startswith("PRIVMSG #marchhare :")
    assert "pong" in out
    assert channel_only.assert_no_worker_nick_privmsg("marchhare-39768", [out]) == []


def test_assert_detects_nick_targets():
    bad = [
        "PRIVMSG bob-marchhare :pong",
        "PRIVMSG bob-flamingo :ACK FR x/y#1",
        "PRIVMSG simon :status",
        "PRIVMSG Jeeves :!list",
    ]
    for line in bad:
        v = channel_only.assert_no_worker_nick_privmsg("flamingo-1", [line])
        assert v, f"should flag {line}"


def test_channel_targets_ok():
    good = [
        "PRIVMSG #flamingo :flamingo-1: ACK FR a/b#1",
        "PRIVMSG #flamingo :DONE FR a/b#1 ok http://x",
        "PRIVMSG #flamingo :!bored",
        "PRIVMSG #flamingo :status idle",
    ]
    assert channel_only.assert_no_worker_nick_privmsg("flamingo-1", good) == []


def test_client_whisper_and_outbox_rewrite(tmp_path: Path):
    home = tmp_path / "h"
    home.mkdir()
    args = _args(home, "flamingo-46804", "#flamingo")
    client = irc_agent.Client(args)
    client.channels = ["#flamingo", "#bobiverse"]
    client.live_nick = "flamingo-46804"
    sent: list[str] = []

    def capture(line: str) -> None:
        sent.append(line)

    client.send = capture  # type: ignore[method-assign]

    # Direct whisper must not hit nick
    client.whisper("bob-flamingo", "pong")
    client.whisper("Jeeves", "ACK FR o/r#1")
    client.say("status ready")

    # Outbox-style
    client.send_privmsg_lines("PRIVMSG bob-marchhare :DONE FR o/r#2 ok")
    client.send_privmsg_lines("PRIVMSG simon :hello")

    assert sent, "expected sends"
    viol = channel_only.assert_no_worker_nick_privmsg("flamingo-46804", sent)
    assert viol == [], f"worker nick PRIVMSG leaked: {viol} sent={sent}"
    assert all("#flamingo" in s or s.upper().startswith("PRIVMSG #") for s in sent if s.upper().startswith("PRIVMSG"))


def test_chair_list_and_help_pm_from_channel(tmp_path: Path):
    """!list / !help in channel → PM to asker; no channel list flood."""
    home = tmp_path / "digest"
    home.mkdir()
    gitclaim.reset_list_rate()
    gitclaim.reset_help_rate()
    # seed one unaccepted row
    gitclaim.enqueue_unaccepted(
        home,
        gitclaim.GitClaim(
            repo="SimonBarnett/agentic_irc",
            task="FR",
            id="#224",
            line="channel-only",
            event="issues",
            action="opened",
        ),
    )
    args = _args(home, "Jeeves", "#bobiverse,#flamingo", chair=True)
    client = irc_agent.Client(args)
    client.channels = ["#bobiverse", "#flamingo"]
    client.live_nick = "Jeeves"
    pms: list[tuple[str, str]] = []
    chans: list[str] = []

    def capture(line: str) -> None:
        if line.upper().startswith("PRIVMSG "):
            rest = line[8:]
            tgt, _, text = rest.partition(" :")
            if tgt.startswith("#"):
                chans.append(line)
            else:
                pms.append((tgt, text))

    client.send = capture  # type: ignore[method-assign]
    # avoid real sleep in tests
    with mock.patch.object(irc_agent, "FLOOD_S", 0):
        assert client._maybe_git_list("flamingo-224", "#flamingo", "!list", to_channel=True)
        assert client._maybe_git_help("flamingo-224", "#flamingo", "!help", to_channel=True)
        assert client._maybe_git_help("simon", "#bobiverse", "!help resync", to_channel=True)

    assert pms, "chair must PM asker"
    assert all(t == "flamingo-224" or t == "simon" for t, _ in pms)
    # no channel flood of list/help bodies
    assert not any("!list" in c and "FR" in c for c in chans)
    assert not any(c.upper().startswith("PRIVMSG #") and "syntax:" in c for c in chans)


def test_help_unknown_and_worker_hides_resync():
    gitclaim.reset_help_rate()
    lines = gitclaim.format_help_lines("!help", asker="flamingo-1")
    assert not any(ln.lower().startswith("!resync") for ln in lines)
    unk = gitclaim.format_help_lines("!help nosuch", asker="flamingo-1")
    assert len(unk) == 1 and "unknown" in unk[0].lower()
    priv = gitclaim.format_help_lines("!help", asker="simon")
    assert any("resync" in ln.lower() for ln in priv)


def test_docs_state_channel_only_rule():
    root = Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert "channel-only" in readme.lower() or "never PRIVMSG a nick" in readme or "never privmsg a nick" in readme.lower()
    doc = root / "docs" / "worker-channel-only.md"
    assert doc.is_file()
    text = doc.read_text(encoding="utf-8")
    assert "PRIVMSG" in text
    assert "!list" in text and "!help" in text
