from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bobcallback
import bobreport
import irc_agent


@pytest.fixture
def recorder(monkeypatch):
    lines: list[str] = []

    def capture(self, line: str) -> None:
        lines.append(line)

    monkeypatch.setattr(irc_agent.Client, "send", capture)
    return lines


def _chair_args(home: Path) -> argparse.Namespace:
    return argparse.Namespace(
        nick="jeeves",
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
        chair=True,
    )


def test_format_github_push():
    payload = {
        "ref": "refs/heads/main",
        "after": "deadbeef0123456789",
        "pusher": {"name": "simon"},
        "repository": {"full_name": "SimonBarnett/agentic_irc"},
        "commits": [{"message": "fix"}],
    }
    line = bobreport.format_github_webhook_announce("push", payload)
    assert line.startswith("GIT push ")
    assert "SimonBarnett/agentic_irc" in line
    assert "main" in line
    assert "deadbeef" in line
    assert "by simon" in line


def test_git_webhook_post_queues_jeeves_outbox(tmp_path):
    allow = {"127.0.0.1"}
    body = json.dumps(
        {
            "zen": "Keep it logically awesome.",
            "repository": {"full_name": "SimonBarnett/agentic_irc"},
            "sender": {"login": "octocat"},
        }
    ).encode()
    digest_before = bobreport.load_digest(tmp_path)
    code, payload = bobcallback.handle_request(
        "POST",
        "/bob/v1/git",
        {"X-GitHub-Event": "ping"},
        body,
        "127.0.0.1",
        tmp_path,
        "",
        allow,
    )
    assert code == 204 and payload == b""
    chair_out = (tmp_path / "chair-outbox.txt").read_text(encoding="utf-8")
    assert chair_out.startswith("PRIVMSG #bobiverse :GIT ping ")
    assert "SimonBarnett/agentic_irc" in chair_out
    regular = tmp_path / "outbox.txt"
    assert (not regular.exists()) or ("GIT" not in regular.read_text(encoding="utf-8"))
    assert not (tmp_path / "git-unaccepted.json").exists()
    assert bobreport.load_digest(tmp_path) == digest_before


def test_git_webhook_requires_event_and_allowlist(tmp_path):
    allow = {"127.0.0.1"}
    body = b'{"repository":{"full_name":"x/y"}}'
    code, _ = bobcallback.handle_request(
        "POST", "/bob/v1/git", {}, body, "127.0.0.1", tmp_path, "", allow
    )
    assert code == 400
    code2, _ = bobcallback.handle_request(
        "POST",
        "/bob/v1/git",
        {"X-GitHub-Event": "ping"},
        body,
        "203.0.113.9",
        tmp_path,
        "",
        allow,
    )
    assert code2 == 403


def _bob_args(home: Path) -> argparse.Namespace:
    args = _chair_args(home)
    args.nick = "bob-ionos"
    args.chair = False
    return args


def test_non_chair_does_not_send_git(tmp_path, monkeypatch, recorder):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    bob = irc_agent.Client(_bob_args(tmp_path))
    bobreport.enqueue_chair_fleet_privmsg(
        bob.home, "GIT pull_request SimonBarnett/agentic_irc opened #1 title by simon"
    )
    bob.sock = object()
    bob.joined.set()
    drained = bob.drain_outbox_once()
    assert not any("GIT" in x for x in drained)
    assert not any("GIT" in x for x in recorder)
    chair = irc_agent.Client(_chair_args(tmp_path))
    chair.sock = object()
    chair.joined.set()
    drained_chair = chair.drain_outbox_once()
    assert any("GIT pull_request" in x for x in drained_chair)
    assert any("GIT pull_request" in x for x in recorder)


def test_chair_sends_git_announce_not_spam(tmp_path, monkeypatch, recorder):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    chair = irc_agent.Client(_chair_args(tmp_path))
    bobreport.enqueue_chair_fleet_privmsg(
        chair.home, "GIT push SimonBarnett/agentic_irc main by simon"
    )
    chair.sock = object()
    chair.joined.set()
    drained = chair.drain_outbox_once()
    assert any("GIT push" in x for x in drained)
    assert any("GIT push" in x for x in recorder)


def test_report_path_unchanged_with_git_route(tmp_path):
    secret = "test-secret"
    allow = {"127.0.0.1"}
    merge = json.dumps(
        {"op": "merge", "machine": "ionos", "pid": 1, "working_on": "git-hook", "kind": "cursor"}
    ).encode()
    code, _ = bobcallback.handle_request(
        "POST",
        "/bob/v1/report",
        {"X-Bob-Secret": secret},
        merge,
        "127.0.0.1",
        tmp_path,
        secret,
        allow,
    )
    assert code == 204
    assert bobreport.load_digest(tmp_path)["machines"]["ionos"]["workers"]["1"]["working_on"] == "git-hook"
    for method, path, expect in (
        ("GET", "/bob/v1/git", 405),
    ):
        c, p = bobcallback.handle_request(method, path, {}, b"", "127.0.0.1", tmp_path, secret, allow)
        assert c == expect and p == b""
    code_g, body_g = bobcallback.handle_request(
        "GET", "/bob/v1/report", {}, b"", "127.0.0.1", tmp_path, secret, allow
    )
    assert code_g == 200
    assert b"git-hook" in body_g
    assert json.loads(body_g.decode("utf-8"))["machines"]["ionos"]["workers"]["1"]["working_on"] == "git-hook"
