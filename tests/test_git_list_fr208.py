"""FR #208 (updated): !list = one line per job, no flood (≤10 jobs, 30s rate)."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import gitclaim
import irc_agent


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


def test_format_empty_and_one_line_per_job(tmp_path):
    assert gitclaim.format_unaccepted_list(tmp_path) == ["queue empty"]
    _enqueue(tmp_path, 2)
    _enqueue(tmp_path, 1)
    lines = gitclaim.format_unaccepted_list(tmp_path)
    # summary + 2 job lines
    assert lines[0] == "2 unaccepted (showing 2)"
    assert lines[1].startswith("#1 FR SimonBarnett/agentic_irc#2")
    assert lines[2].startswith("#2 FR SimonBarnett/agentic_irc#1")
    assert "title for job" in lines[1]
    # no URL spam on the line (title only)
    assert "https://" not in lines[1]
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
    one = gitclaim.format_list_line(1, gitclaim.load_unaccepted(tmp_path)[-1], line_max=80)
    assert len(one.encode("utf-8")) <= 80
    assert one.startswith("#1 ")


def test_cap_10_and_more_hint_for_30_jobs(tmp_path):
    for i in range(1, 31):
        _enqueue(tmp_path, i)
    lines = gitclaim.format_unaccepted_list(tmp_path)
    # summary + 10 jobs + more <= 12
    assert len(lines) <= 12
    assert lines[0] == "30 unaccepted (showing 10)"
    job_lines = [x for x in lines if x.startswith("#")]
    assert len(job_lines) == 10
    assert lines[-1] == "+20 more; !list all"
    for jl in job_lines:
        assert len(jl.encode("utf-8")) <= gitclaim.LIST_LINE_MAX
    # !list all shows all
    all_lines = gitclaim.format_unaccepted_list(tmp_path, list_all=True)
    assert len([x for x in all_lines if x.startswith("#")]) == 30


def test_list_filters_task_and_repo(tmp_path):
    _enqueue(tmp_path, 1, task="FR", repo="SimonBarnett/a")
    gitclaim.enqueue_unaccepted(
        tmp_path,
        gitclaim.GitClaim(
            "SimonBarnett/b",
            "MRB",
            "#2",
            "pull_request",
            "opened",
            "GIT pull_request SimonBarnett/b opened #2 t by s",
        ),
    )
    fr_only = gitclaim.format_unaccepted_list(tmp_path, task_filter="FR")
    assert any("#1" in x for x in fr_only)
    assert not any("MRB" in x and "#2" in x for x in fr_only if x.startswith("#"))
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
    assert sent
    assert all(x.startswith("PRIVMSG simon :") for x in sent)
    assert not any(x.startswith("PRIVMSG #bobiverse :") for x in sent)
    assert any("#1 FR SimonBarnett/agentic_irc#5" in x for x in sent)


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


def test_rate_limit_30s_one_notice(tmp_path, monkeypatch):
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
    full = list(sent)
    sent.clear()
    # five rapid repeats → one short notice each (not full flood)
    for _ in range(5):
        c.handle_privmsg("bob!u@h", "#bobiverse", "!list")
    assert len(sent) == 5
    assert all("list sent" in x and "ago" in x for x in sent)
    assert all(x.startswith("PRIVMSG bob :") for x in sent)
    # after 30s window, full list again
    clock["t"] += gitclaim.LIST_RATE_S + 0.1
    sent.clear()
    c.handle_privmsg("bob!u@h", "#bobiverse", "!list")
    assert any("queue empty" in x for x in sent)
    assert len(full) >= 1


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


def test_constants_match_updated_spec():
    assert gitclaim.LIST_MAX_LINES == 10
    assert gitclaim.LIST_RATE_S == 30.0
    assert gitclaim.LIST_LINE_MAX <= 400
