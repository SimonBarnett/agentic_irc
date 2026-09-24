"""Webhook GIT queue: !BORED claims the top job. !ACCEPT does not."""

from __future__ import annotations

import argparse
import json
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bobcallback
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
    ready_line = "GIT pull_request SimonBarnett/agentic_irc ready_for_review #7 ear by simon"
    ready = gitclaim.claim_from_payload(
        "pull_request",
        {
            "action": "ready_for_review",
            "pull_request": {"number": 7, "title": "ear"},
            "repository": {"full_name": "SimonBarnett/agentic_irc"},
        },
        line=ready_line,
    )
    assert ready is not None and ready.task == "MRB"
    assert gitclaim.parse_git_announce(ready_line) == ready
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
    assert gitclaim.parse_accept("FILE v1 ACCEPT abcdef") is None
    assert gitclaim.is_accept_command("FILE v1 ACCEPT abcdef") is False
    assert gitclaim.parse_accept("!ACCEPT SimonBarnett/agentic_irc PR #1") == (
        "SimonBarnett/agentic_irc",
        "PR",
        "#1",
    )
    assert gitclaim.parse_accept("!ACCEPT SimonBarnett/agentic_irc BUILD #2")[1] == "BUILD"
    assert bobtalk.is_protocol_line("!BORED")
    assert bobtalk.is_protocol_line("!ACCEPT SimonBarnett/agentic_irc MRB #2")
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
    assert not gitclaim.queue_path(tmp_path).exists()
    assert not (tmp_path / "git-unaccepted.json").exists()
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
    assert push.ok and not gitclaim.queue_path(tmp_path).exists()
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
    again = bobreport.apply_git_webhook(tmp_path, "issues", issue)
    assert again.ok
    assert len(gitclaim.load_unaccepted(tmp_path)) == 1
    listed = bobreport.build_digest_object(tmp_path, "Jeeves")["queue"]
    assert listed["unaccepted"][0]["id"] == "#42"
    assert listed["accepted"] == []


def test_git_claim_post_is_atomic_and_get_lists_it(tmp_path):
    assert gitclaim.enqueue_unaccepted(tmp_path, _claim(1)) == "added"
    assert gitclaim.enqueue_unaccepted(tmp_path, _claim(2)) == "added"
    code, body = bobcallback.handle_request(
        "POST",
        "/bob/v1/report",
        {"X-Bob-Secret": "s"},
        json.dumps({"op": "git-claim", "nick": "w-fl-4412", "channel": "#flamingo"}).encode(),
        "127.0.0.1",
        tmp_path,
        "s",
        {"127.0.0.1"},
    )
    assert code == 200
    claimed = json.loads(body.decode())["claimed"]
    assert claimed["repo"] == "SimonBarnett/agentic_irc"
    assert claimed["task"] == "MRB" and claimed["id"] == "#1"
    assert claimed["nick"] == "w-fl-4412"
    listed = json.loads(
        bobcallback.handle_request(
            "GET", "/bob/v1/report", {}, b"", "127.0.0.1", tmp_path, "s", {"127.0.0.1"}
        )[1].decode()
    )["queue"]
    assert [row["id"] for row in listed["unaccepted"]] == ["#2"]
    assert [row["id"] for row in listed["accepted"]] == ["#1"]
    code2, body2 = bobcallback.handle_request(
        "POST",
        "/bob/v1/report",
        {"X-Bob-Secret": "s"},
        json.dumps({"op": "git-claim", "nick": "w-mh-3", "channel": "#marchhare"}).encode(),
        "127.0.0.1",
        tmp_path,
        "s",
        {"127.0.0.1"},
    )
    assert code2 == 200
    assert json.loads(body2.decode())["claimed"]["id"] == "#2"


def test_legacy_files_import_once(tmp_path):
    (tmp_path / "git-unaccepted.json").write_text(
        json.dumps(
            {
                "v": 1,
                "items": [
                    {
                        "repo": "SimonBarnett/agentic_irc",
                        "task": "PR",
                        "id": "#9",
                        "ts": "2026-09-24T00:00:00Z",
                        "line": "GIT issues SimonBarnett/agentic_irc opened #9 t by s",
                        "event": "issues",
                        "action": "opened",
                        "seq": 1,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    rows = gitclaim.load_unaccepted(tmp_path)
    assert rows[0]["id"] == "#9"
    assert gitclaim.queue_path(tmp_path).exists()


def test_idle_clears_working_on_agent_model(tmp_path):
    out = bobreport.apply_callback(
        tmp_path,
        {
            "op": "merge",
            "machine": "flamingo",
            "pid": 4412,
            "nick": "w-fl-4412",
            "kind": "cursor",
            "state": "running",
            "online": True,
            "working_on": "SimonBarnett/agentic_irc PR #42",
            "agent": "cursor",
            "model": "grok",
        },
    )
    assert out.ok
    worker = bobreport.load_digest(tmp_path)["machines"]["flamingo"]["workers"]["4412"]
    assert worker["working_on"] == "SimonBarnett/agentic_irc PR #42"
    assert worker["agent"] == "cursor"
    assert worker["model"] == "grok"
    cleared = bobreport.apply_callback(
        tmp_path,
        {
            "op": "merge",
            "machine": "flamingo",
            "pid": 4412,
            "nick": "w-fl-4412",
            "kind": "cursor",
            "state": "idle",
            "online": True,
        },
    )
    assert cleared.ok
    worker = bobreport.load_digest(tmp_path)["machines"]["flamingo"]["workers"]["4412"]
    assert worker["state"] == "idle"
    assert worker["working_on"] == ""
    assert "agent" not in worker and "model" not in worker


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


def _serve(home: Path, monkeypatch):
    secret = "test-secret"
    httpd = bobcallback.serve(home, "127.0.0.1", 0, secret, {"127.0.0.1"})
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = httpd.server_address[1]
    url = f"http://127.0.0.1:{port}/bob/v1/report"
    monkeypatch.setenv("BOB_REPORT_SECRET", secret)
    monkeypatch.setenv("AGENTIC_IRC_REPORT_URL", url)
    monkeypatch.setenv("BOB_REPORT_URL", url)
    return httpd, thread


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


def test_bored_claims_top_via_webhook_accept_is_noop(tmp_path, monkeypatch):
    httpd, thread = _serve(tmp_path, monkeypatch)
    try:
        clock = {"t": 1_000_000.0}
        chair, sent = _client(tmp_path, monkeypatch, "Jeeves", True, clock)
        assert gitclaim.enqueue_unaccepted(tmp_path, _claim(1)) == "added"
        assert gitclaim.enqueue_unaccepted(tmp_path, _claim(2)) == "added"
        chair.handle_privmsg("w-fl-4412!u@h", "#flamingo", "!BORED")
        assert sent == ["PRIVMSG #flamingo :SimonBarnett/agentic_irc MRB #1"]
        assert [row["id"] for row in gitclaim.load_unaccepted(tmp_path)] == ["#2"]
        assert gitclaim.load_accepted(tmp_path)[0]["id"] == "#1"
        sent.clear()
        chair.handle_privmsg(
            "w-fl-4412!u@h",
            "#flamingo",
            "!ACCEPT SimonBarnett/agentic_irc MRB #2",
        )
        assert sent == []
        assert [row["id"] for row in gitclaim.load_unaccepted(tmp_path)] == ["#2"]
        sent.clear()
        chair.handle_privmsg("w-fl-4412!u@h", "#flamingo", "!BORED")
        assert sent == ["PRIVMSG #flamingo :NAK !BORED wait"]
        assert [row["id"] for row in gitclaim.load_unaccepted(tmp_path)] == ["#2"]
        clock["t"] += gitclaim.IDLE_S + 1
        sent.clear()
        chair.handle_privmsg("w-mh-3!u@h", "#marchhare", "!bored")
        assert sent == ["PRIVMSG #marchhare :SimonBarnett/agentic_irc MRB #2"]
        assert gitclaim.load_unaccepted(tmp_path) == []
    finally:
        httpd.shutdown()
        thread.join(timeout=2)


def test_bored_filters_and_empty(tmp_path, monkeypatch):
    httpd, thread = _serve(tmp_path, monkeypatch)
    try:
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
        clock["t"] += gitclaim.IDLE_S + 1
        sent.clear()
        chair.handle_privmsg("w-mh-3!u@h", "#marchhare", "!BORED")
        assert sent == ["PRIVMSG #marchhare :SimonBarnett/agentic_irc PR #4"]
        assert gitclaim.load_unaccepted(tmp_path) == []
        sent.clear()
        chair.handle_privmsg("w-io-2!u@h", "#ionos", "!BORED")
        assert sent == ["PRIVMSG #ionos :no jobs"]
    finally:
        httpd.shutdown()
        thread.join(timeout=2)


def test_bob_does_not_auto_accept_and_file_accept_is_separate(tmp_path, monkeypatch):
    clock = {"t": 80.0}
    bob, sent = _client(tmp_path, monkeypatch, "bob-flamingo", False, clock)
    line = "GIT issues SimonBarnett/agentic_irc opened #9 ship by friday by simon"
    bob.handle_privmsg("Jeeves!u@h", "#bobiverse", line)
    bob.handle_privmsg("w-fl-4412!u@h", "#flamingo", "!BORED")
    assert sent == []
    assert not gitclaim.queue_path(tmp_path).exists()
    chair, chair_sent = _client(tmp_path, monkeypatch, "Jeeves", True, clock)
    chair.handle_privmsg("w-fl-4412!u@h", "#flamingo", "FILE v1 ACCEPT abcdef")
    chair.handle_privmsg("w-fl-4412!u@h", "#flamingo", "!ACCEPT SimonBarnett/agentic_irc PR #9")
    assert chair_sent == []
    assert gitclaim.load_accepted(tmp_path) == []
