"""FR #208: Jeeves !list PMs unaccepted queue; never channel."""
from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import gitclaim
import irc_agent
import bobreport


def _args(home: Path, nick: str = "Jeeves", chair: bool = True) -> argparse.Namespace:
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


def _enqueue(home: Path, n: int, task: str = "FR", repo: str = "SimonBarnett/agentic_irc") -> None:
    line = f"GIT issues {repo} opened #{n} title for job {n} by simon"
    gitclaim.enqueue_unaccepted(
        home,
        gitclaim.GitClaim(repo, task, f"#{n}", "issues", "opened", line),
    )


def test_format_empty_and_order_and_truncation(tmp_path):
    assert gitclaim.format_unaccepted_list(tmp_path) == ["queue empty"]
    _enqueue(tmp_path, 2)
    _enqueue(tmp_path, 1)
    lines = gitclaim.format_unaccepted_list(tmp_path)
    assert lines[0] == "unaccepted 2"
    # claim order by seq (enqueue order)
    assert "FR SimonBarnett/agentic_irc#2" in lines[1]
    assert "FR SimonBarnett/agentic_irc#1" in lines[2]
    assert "https://github.com/" in lines[1]
    long_title = "x" * 500
    gitclaim.enqueue_unaccepted(
        tmp_path,
        gitclaim.GitClaim(
            "SimonBarnett/x",
            "MRB",
            "#9",
            "pull_request",
            "opened",
            f"GIT pull_request SimonBarnett/x opened #9 {long_title} by s",
        ),
    )
    one = gitclaim.format_list_line(1, 1, gitclaim.load_unaccepted(tmp_path)[-1], line_max=80)
    assert len(one) <= 80
    assert one.endswith("…") or len(one) <= 80


def test_list_cap_and_more_footer(tmp_path):
    for i in range(1, 51):
        _enqueue(tmp_path, i)
    lines = gitclaim.format_unaccepted_list(tmp_path, max_lines=30)
    assert lines[0].startswith("unaccepted 30/50")
    assert len([x for x in lines if x[:1].isdigit()]) == 30
    assert lines[-1] == "... +20 more (see webhook report)"


def test_list_filters_task_and_repo(tmp_path):
    _enqueue(tmp_path, 1, task="FR", repo="SimonBarnett/a")
    gitclaim.enqueue_unaccepted(
        tmp_path,
        gitclaim.GitClaim(
            "SimonBarnett/b", "MRB", "#2", "pull_request", "opened", "GIT pull_request SimonBarnett/b opened #2 t by s"
        ),
    )
    fr_only = gitclaim.format_unaccepted_list(tmp_path, task_filter="FR")
    assert all(" FR " in x or x.startswith("unaccepted") for x in fr_only)
    assert any("#1" in x for x in fr_only)
    assert not any("#2" in x for x in fr_only)
    repo_b = gitclaim.format_unaccepted_list(tmp_path, repo_filter="SimonBarnett/b")
    assert any("#2" in x for x in repo_b)


def test_channel_list_pms_only_not_channel(tmp_path, monkeypatch):
    gitclaim.reset_list_rate()
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    monkeypatch.setattr(irc_agent.time, "sleep", lambda *_a, **_k: None)
    sent: list[str] = []
    monkeypatch.setattr(irc_agent.Client, "send", lambda self, line: sent.append(line))
    _enqueue(tmp_path, 5)
    c = irc_agent.Client(_args(tmp_path))
    c.sock = object()
    c.joined.set()
    c.handle_privmsg("simon!u@h", "#bobiverse", "!list")
    assert sent, "expected PM lines"
    assert all(x.startswith("PRIVMSG simon :") for x in sent)
    assert not any(x.startswith("PRIVMSG #bobiverse :") for x in sent)
    assert any("unaccepted" in x for x in sent)
    assert any("FR SimonBarnett/agentic_irc#5" in x for x in sent)


def test_pm_list_works_same(tmp_path, monkeypatch):
    gitclaim.reset_list_rate()
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    monkeypatch.setattr(irc_agent.time, "sleep", lambda *_a, **_k: None)
    sent: list[str] = []
    monkeypatch.setattr(irc_agent.Client, "send", lambda self, line: sent.append(line))
    c = irc_agent.Client(_args(tmp_path))
    c.sock = object()
    c.joined.set()
    c.handle_privmsg("alice!u@h", "Jeeves", "!list")
    assert all(x.startswith("PRIVMSG alice :") for x in sent)
    assert any("queue empty" in x for x in sent)


def test_rate_limit_second_list(tmp_path, monkeypatch):
    gitclaim.reset_list_rate()
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    monkeypatch.setattr(irc_agent.time, "sleep", lambda *_a, **_k: None)
    clock = {"t": 1000.0}
    monkeypatch.setattr(irc_agent.time, "time", lambda: clock["t"])
    sent: list[str] = []
    monkeypatch.setattr(irc_agent.Client, "send", lambda self, line: sent.append(line))
    c = irc_agent.Client(_args(tmp_path))
    c.sock = object()
    c.joined.set()
    c.handle_privmsg("bob!u@h", "#bobiverse", "!list")
    n1 = len(sent)
    sent.clear()
    c.handle_privmsg("bob!u@h", "#bobiverse", "!list")
    assert sent == ["PRIVMSG bob :NAK !list rate"]
    clock["t"] += gitclaim.LIST_RATE_S + 0.1
    sent.clear()
    c.handle_privmsg("bob!u@h", "#bobiverse", "!list")
    assert any("queue empty" in x for x in sent)
    assert n1 >= 1


def test_non_chair_ignores_list(tmp_path, monkeypatch):
    gitclaim.reset_list_rate()
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    sent: list[str] = []
    monkeypatch.setattr(irc_agent.Client, "send", lambda self, line: sent.append(line))
    bob = irc_agent.Client(_args(tmp_path, nick="bob-marchhare", chair=False))
    bob.sock = object()
    bob.joined.set()
    bob.handle_privmsg("simon!u@h", "#bobiverse", "!list")
    assert sent == []
