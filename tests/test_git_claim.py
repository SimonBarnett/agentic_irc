"""Jeeves GIT queue: parse, FIFO, !BORED, !ACCEPT. Not FILE v1 ACCEPT."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bobreport
import bobtalk
import gitclaim
import irc_agent


def _claim(n: int, task: str = "MRB", event: str = "pull_request", action: str = "opened") -> gitclaim.GitClaim:
    line = f"GIT {event} SimonBarnett/agentic_irc {action} #{n} title by simon"
    return gitclaim.GitClaim(
        repo="SimonBarnett/agentic_irc",
        task=task,
        id=f"#{n}",
        event=event,
        action=action,
        line=line,
    )


def test_parse_allowlist_and_skip_ping():
    issue = bobreport.format_github_webhook_announce(
        "issues",
        {
            "action": "opened",
            "issue": {"number": 42, "title": "ship by friday"},
            "repository": {"full_name": "SimonBarnett/agentic_irc"},
            "sender": {"login": "simon"},
        },
    )
    parsed = gitclaim.parse_git_announce(issue)
    assert parsed is not None
    assert (parsed.repo, parsed.task, parsed.id, parsed.event, parsed.action) == (
        "SimonBarnett/agentic_irc",
        "PR",
        "#42",
        "issues",
        "opened",
    )
    pr = bobreport.format_github_webhook_announce(
        "pull_request",
        {
            "action": "opened",
            "pull_request": {"number": 7, "title": "ear"},
            "repository": {"full_name": "SimonBarnett/agentic_irc"},
            "sender": {"login": "simon"},
        },
    )
    opened = gitclaim.parse_git_announce(pr)
    assert opened is not None and opened.task == "MRB" and opened.id == "#7"
    ready = gitclaim.claim_from_payload(
        "pull_request",
        {
            "action": "ready_for_review",
            "pull_request": {"number": 7, "title": "ear"},
            "repository": {"full_name": "SimonBarnett/agentic_irc"},
        },
        line="GIT pull_request SimonBarnett/agentic_irc ready_for_review #7 ear by simon",
    )
    assert ready is not None and ready.task == "MRB"
    announced = gitclaim.parse_git_announce(
        "GIT pull_request SimonBarnett/agentic_irc ready_for_review #7 ear by simon"
    )
    assert announced == ready
    assert gitclaim.accept_allowed("w-fl-4412", "#bobiverse")
    assert gitclaim.accept_allowed("w-fl-4412", "#flamingo")
    assert not gitclaim.accept_allowed("w-fl-4412", "#ionos")
    assert gitclaim.accept_allowed("bob-ionos", "#bobiverse")
    assert gitclaim.accept_allowed("bob-ionos", "#ionos")
    assert not gitclaim.accept_allowed("simon", "#bobiverse")
    assert not gitclaim.accept_allowed("bob-flamingo", "#ionos")
    ping = bobreport.format_github_webhook_announce(
        "ping",
        {
            "zen": "Keep it logically awesome.",
            "repository": {"full_name": "SimonBarnett/agentic_irc"},
            "sender": {"login": "octocat"},
        },
    )
    assert ping.startswith("GIT ping ")
    assert gitclaim.parse_git_announce(ping) is None
    assert gitclaim.claim_from_payload("ping", {"zen": "x", "repository": {"full_name": "a/b"}}) is None
    assert (
        gitclaim.claim_from_payload(
            "push",
            {
                "ref": "refs/heads/main",
                "after": "deadbeef0123456789",
                "repository": {"full_name": "SimonBarnett/agentic_irc"},
                "commits": [{"message": "fix"}],
            },
        )
        is None
    )
    assert (
        gitclaim.claim_from_payload(
            "pull_request",
            {
                "action": "closed",
                "pull_request": {"number": 3},
                "repository": {"full_name": "SimonBarnett/agentic_irc"},
            },
        )
        is None
    )
    assert (
        gitclaim.claim_from_payload(
            "issues",
            {
                "action": "edited",
                "issue": {"number": 3},
                "repository": {"full_name": "SimonBarnett/agentic_irc"},
            },
        )
        is None
    )
    assert gitclaim.parse_accept("FILE v1 ACCEPT abcdef") is None
    assert gitclaim.is_accept_command("FILE v1 ACCEPT abcdef") is False
    assert gitclaim.parse_accept("!accept SimonBarnett/agentic_irc pr #1") is None
    assert gitclaim.parse_accept("!ACCEPT SimonBarnett/agentic_irc PR #1") == (
        "SimonBarnett/agentic_irc",
        "PR",
        "#1",
    )
    assert bobtalk.is_protocol_line("!BORED")
    assert bobtalk.is_protocol_line("!ACCEPT SimonBarnett/agentic_irc MRB #2")
    assert bobtalk.is_protocol_line("!TASK SimonBarnett/agentic_irc PR #9")
    assert bobtalk.is_protocol_line("FILE v1 ACCEPT abcdef")


def test_webhook_queues_issue_not_ping_or_push(tmp_path):
    ping = bobreport.apply_git_webhook(
        tmp_path,
        "ping",
        {
            "zen": "Keep it logically awesome.",
            "repository": {"full_name": "SimonBarnett/agentic_irc"},
            "sender": {"login": "octocat"},
        },
    )
    assert ping.ok and ping.announced
    assert not gitclaim.unaccepted_path(tmp_path).exists()
    push = bobreport.apply_git_webhook(
        tmp_path,
        "push",
        {
            "ref": "refs/heads/main",
            "after": "deadbeef0123456789",
            "repository": {"full_name": "SimonBarnett/agentic_irc"},
            "pusher": {"name": "simon"},
            "commits": [{"message": "x"}],
        },
    )
    assert push.ok and not gitclaim.unaccepted_path(tmp_path).exists()
    issue = {
        "action": "opened",
        "issue": {"number": 42, "title": "ship by friday"},
        "repository": {"full_name": "SimonBarnett/agentic_irc"},
        "sender": {"login": "simon"},
    }
    queued = bobreport.apply_git_webhook(tmp_path, "issues", issue)
    assert queued.ok
    rows = gitclaim.load_unaccepted(tmp_path)
    assert len(rows) == 1
    assert rows[0]["task"] == "PR" and rows[0]["id"] == "#42"
    assert rows[0]["line"].startswith("GIT issues ")
    assert "ship by friday" in rows[0]["line"]
    again = bobreport.apply_git_webhook(tmp_path, "issues", issue)
    assert again.ok
    assert len(gitclaim.load_unaccepted(tmp_path)) == 1
    chair = (tmp_path / "chair-outbox.txt").read_text(encoding="utf-8")
    assert chair.count("GIT issues ") == 2
    assert "PRIVMSG #bobiverse :GIT issues " in chair


def _args(home: Path, nick: str, chair: bool) -> argparse.Namespace:
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
        chair=chair,
    )


def _client(tmp_path: Path, monkeypatch, nick: str, chair: bool, clock: dict):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    sent: list[str] = []

    def _send(self, line: str) -> None:
        sent.append(line)

    monkeypatch.setattr(irc_agent.Client, "send", _send)
    monkeypatch.setattr(irc_agent.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(irc_agent.time, "time", lambda: clock["t"])
    client = irc_agent.Client(_args(tmp_path, nick, chair))
    return client, sent


def _busy(home: Path, text: str) -> None:
    doc = bobreport.load_digest(home)
    doc["machines"]["flamingo"]["workers"]["4412"] = {
        "pid": "4412",
        "nick": "w-fl-4412",
        "kind": "cursor",
        "state": "running",
        "working_on": text,
        "key": "flamingo:4412",
    }
    bobreport.save_digest(home, doc)


def test_bored_fifo_then_accept_and_second_is_nak(tmp_path, monkeypatch):
    clock = {"t": 1_000_000.0}
    chair, sent = _client(tmp_path, monkeypatch, "Jeeves", True, clock)
    assert "#flamingo" in [c.lower() for c in chair.channels]
    assert gitclaim.enqueue_unaccepted(tmp_path, _claim(1)) == "added"
    assert gitclaim.enqueue_unaccepted(tmp_path, _claim(2)) == "added"
    assert gitclaim.enqueue_unaccepted(tmp_path, _claim(1)) == "duplicate"
    chair.handle_privmsg("w-fl-4412!u@h", "#flamingo", "!BORED")
    assert sent == ["PRIVMSG #flamingo :!TASK SimonBarnett/agentic_irc MRB #1"]
    sent.clear()
    chair.handle_privmsg("w-fl-4412!u@h", "#flamingo", "!BORED")
    assert sent == ["PRIVMSG #flamingo :NAK !BORED wait"]
    sent.clear()
    chair.handle_privmsg(
        "w-fl-4412!u@h",
        "#flamingo",
        "!ACCEPT SimonBarnett/agentic_irc MRB #1",
    )
    assert sent == ["PRIVMSG #flamingo :OK !ACCEPT SimonBarnett/agentic_irc MRB #1"]
    assert gitclaim.load_unaccepted(tmp_path)[0]["id"] == "#2"
    assert len(gitclaim.load_accepted(tmp_path)) == 1
    sent.clear()
    chair.handle_privmsg(
        "w-io-9!u@h",
        "#ionos",
        "!ACCEPT SimonBarnett/agentic_irc MRB #1",
    )
    assert sent == ["PRIVMSG #ionos :NAK !ACCEPT SimonBarnett/agentic_irc MRB #1"]
    assert len(gitclaim.load_accepted(tmp_path)) == 1
    sent.clear()
    clock["t"] += gitclaim.IDLE_S + 1
    chair.handle_privmsg("w-fl-4412!u@h", "#flamingo", "!bored")
    assert sent == ["PRIVMSG #flamingo :!TASK SimonBarnett/agentic_irc MRB #2"]


def test_bored_filters(tmp_path, monkeypatch):
    clock = {"t": 5_000.0}
    chair, sent = _client(tmp_path, monkeypatch, "Jeeves", True, clock)
    gitclaim.enqueue_unaccepted(tmp_path, _claim(4, task="PR", event="issues", action="opened"))
    chair.handle_privmsg("w-fl-4412!u@h", "#ionos", "!BORED")
    chair.handle_privmsg("bob-flamingo!u@h", "#flamingo", "!BORED")
    chair.handle_privmsg("w-fl-4412!u@h", "#flamingo", "!BORED please")
    chair.handle_privmsg("simon!u@h", "#flamingo", "!BORED")
    assert sent == []
    assert len(gitclaim.load_unaccepted(tmp_path)) == 1
    chair.handle_privmsg("w-fl-4412!u@h", "#flamingo", "hello from the shop")
    sent.clear()
    chair.handle_privmsg("w-fl-4412!u@h", "#flamingo", "!BORED")
    assert sent == ["PRIVMSG #flamingo :NAK !BORED wait"]
    clock["t"] += gitclaim.IDLE_S + 1
    _busy(tmp_path, "implement #4")
    sent.clear()
    chair.handle_privmsg("w-fl-4412!u@h", "#flamingo", "!BORED")
    assert sent == ["PRIVMSG #flamingo :NAK !BORED busy"]
    assert len(gitclaim.load_unaccepted(tmp_path)) == 1
    _busy(tmp_path, "")
    sent.clear()
    chair.handle_privmsg("w-fl-4412!u@h", "#flamingo", "!BORED")
    assert sent == ["PRIVMSG #flamingo :NAK !BORED wait"]
    clock["t"] += gitclaim.IDLE_S + 1
    sent.clear()
    empty, empty_sent = _client(tmp_path, monkeypatch, "Jeeves", True, clock)
    empty.handle_privmsg("w-mh-3!u@h", "#marchhare", "!BORED")
    assert empty_sent == ["PRIVMSG #marchhare :!TASK SimonBarnett/agentic_irc PR #4"]


def test_empty_queue_and_bob_fast_path(tmp_path, monkeypatch):
    clock = {"t": 50.0}
    chair, sent = _client(tmp_path, monkeypatch, "Jeeves", True, clock)
    chair.handle_privmsg("w-io-2!u@h", "#ionos", "!BORED")
    assert sent == ["PRIVMSG #ionos :NAK !BORED empty"]
    gitclaim.enqueue_unaccepted(tmp_path, _claim(8, task="PR", event="issues", action="opened"))
    sent.clear()
    chair.handle_privmsg("bob-ionos!u@h", "#bobiverse", "!ACCEPT SimonBarnett/agentic_irc PR #8")
    assert sent == ["PRIVMSG #bobiverse :OK !ACCEPT SimonBarnett/agentic_irc PR #8"]
    assert gitclaim.load_unaccepted(tmp_path) == []
    sent.clear()
    gitclaim.enqueue_unaccepted(tmp_path, _claim(9))
    chair.handle_privmsg("bob-flamingo!u@h", "#ionos", "!ACCEPT SimonBarnett/agentic_irc MRB #9")
    assert sent == []
    assert gitclaim.load_unaccepted(tmp_path)[0]["id"] == "#9"


def test_bob_does_not_auto_accept_git_and_file_accept_is_separate(tmp_path, monkeypatch):
    clock = {"t": 80.0}
    bob, sent = _client(tmp_path, monkeypatch, "bob-flamingo", False, clock)
    line = "GIT issues SimonBarnett/agentic_irc opened #9 ship by friday by simon"
    bob.handle_privmsg("Jeeves!u@h", "#bobiverse", line)
    bob.handle_privmsg("w-fl-4412!u@h", "#flamingo", "!BORED")
    assert sent == []
    assert not gitclaim.unaccepted_path(tmp_path).exists()
    chair, chair_sent = _client(tmp_path, monkeypatch, "Jeeves", True, clock)
    chair.handle_privmsg("Jeeves!x@h", "#bobiverse", line)
    chair.handle_privmsg("w-fl-4412!u@h", "#flamingo", "FILE v1 ACCEPT abcdef")
    assert not any("!ACCEPT" in row or "!TASK" in row or "!BORED" in row for row in chair_sent)
    assert gitclaim.load_accepted(tmp_path) == []
    chair.handle_privmsg("w-fl-4412!u@h", "#flamingo", "!ACCEPT only-three")
    assert chair_sent == []
