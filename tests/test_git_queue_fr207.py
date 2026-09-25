"""FR #207: deterministic GIT queue — FR kind, supersede, ACK accept, resync."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bobreport
import gitclaim


def test_issue_opened_and_reopened_queue_as_fr(tmp_path):
    opened = gitclaim.claim_from_payload(
        "issues",
        {
            "action": "opened",
            "issue": {"number": 19, "title": "x"},
            "repository": {"full_name": "SimonBarnett/skills-visionary"},
        },
    )
    assert opened is not None and opened.task == "FR" and opened.id == "#19"
    assert gitclaim.enqueue_unaccepted(tmp_path, opened) == "added"
    rows = gitclaim.load_unaccepted(tmp_path)
    assert rows[0]["task"] == "FR" and rows[0]["id"] == "#19"

    reopened = gitclaim.claim_from_payload(
        "issues",
        {
            "action": "reopened",
            "issue": {"number": 327, "title": "ergo"},
            "repository": {"full_name": "SimonBarnett/agentic_build"},
        },
    )
    assert reopened is not None and reopened.task == "FR"
    assert gitclaim.enqueue_unaccepted(tmp_path, reopened) == "added"
    ids = {(r["repo"], r["id"], r["task"]) for r in gitclaim.load_unaccepted(tmp_path)}
    assert ("SimonBarnett/agentic_build", "#327", "FR") in ids


def test_pr_supersedes_fr_and_idempotent_replay(tmp_path):
    fr = gitclaim.GitClaim(
        "SimonBarnett/AgentMonitor", "FR", "#88", "issues", "opened", "GIT issues ..."
    )
    assert gitclaim.enqueue_unaccepted(tmp_path, fr) == "added"
    pr = gitclaim.claim_from_payload(
        "pull_request",
        {
            "action": "opened",
            "pull_request": {
                "number": 87,
                "title": "fix watch",
                "body": "Closes #88",
            },
            "repository": {"full_name": "SimonBarnett/AgentMonitor"},
        },
    )
    assert pr is not None and pr.task == "MRB" and pr.refs == ("#88",)
    assert gitclaim.enqueue_unaccepted(tmp_path, pr) == "added"
    rows = gitclaim.load_unaccepted(tmp_path)
    assert all(not (r["task"] == "FR" and r["id"] == "#88") for r in rows)
    assert any(r["task"] == "MRB" and r["id"] == "#87" for r in rows)
    # replay same PR
    assert gitclaim.enqueue_unaccepted(tmp_path, pr) == "duplicate"
    assert sum(1 for r in gitclaim.load_unaccepted(tmp_path) if r["id"] == "#87") == 1


def test_pr_closed_unmerged_restores_fr(tmp_path):
    pr = gitclaim.GitClaim(
        "SimonBarnett/agentic_irc",
        "MRB",
        "#203",
        "pull_request",
        "opened",
        "",
        refs=("#204",),
    )
    gitclaim.enqueue_unaccepted(tmp_path, pr)
    closed = gitclaim.claim_from_payload(
        "pull_request",
        {
            "action": "closed",
            "pull_request": {
                "number": 203,
                "merged": False,
                "title": "x",
                "body": "Fixes #204",
            },
            "repository": {"full_name": "SimonBarnett/agentic_irc"},
        },
    )
    assert closed is not None and closed.merged is False
    gitclaim.enqueue_unaccepted(tmp_path, closed)
    rows = gitclaim.load_unaccepted(tmp_path)
    assert not any(r["task"] == "MRB" and r["id"] == "#203" for r in rows)
    assert any(r["task"] == "FR" and r["id"] == "#204" for r in rows)


def test_pr_merged_adds_uat_for_linked_issue(tmp_path):
    pr = gitclaim.GitClaim(
        "SimonBarnett/skills-visionary",
        "MRB",
        "#18",
        "pull_request",
        "opened",
        "",
        refs=("#19",),
    )
    gitclaim.enqueue_unaccepted(tmp_path, pr)
    merged = gitclaim.claim_from_payload(
        "pull_request",
        {
            "action": "closed",
            "pull_request": {
                "number": 18,
                "merged": True,
                "title": "gate",
                "body": "Closes #19",
            },
            "repository": {"full_name": "SimonBarnett/skills-visionary"},
        },
    )
    gitclaim.enqueue_unaccepted(tmp_path, merged)
    rows = gitclaim.load_unaccepted(tmp_path)
    assert not any(r["task"] == "MRB" and r["id"] == "#18" for r in rows)
    assert any(r["task"] == "UAT" and r["id"] == "#19" for r in rows)


def test_issue_closed_removes_fr_and_uat(tmp_path):
    gitclaim.enqueue_unaccepted(
        tmp_path,
        gitclaim.GitClaim("SimonBarnett/x", "FR", "#1", "issues", "opened", ""),
    )
    gitclaim.enqueue_unaccepted(
        tmp_path,
        gitclaim.GitClaim("SimonBarnett/x", "UAT", "#2", "issues", "uat", ""),
    )
    closed = gitclaim.claim_from_payload(
        "issues",
        {
            "action": "closed",
            "issue": {"number": 1},
            "repository": {"full_name": "SimonBarnett/x"},
        },
    )
    gitclaim.enqueue_unaccepted(tmp_path, closed)
    rows = gitclaim.load_unaccepted(tmp_path)
    assert not any(r["id"] == "#1" for r in rows)
    assert any(r["id"] == "#2" for r in rows)
    closed2 = gitclaim.claim_from_payload(
        "issues",
        {
            "action": "closed",
            "issue": {"number": 2},
            "repository": {"full_name": "SimonBarnett/x"},
        },
    )
    gitclaim.enqueue_unaccepted(tmp_path, closed2)
    assert not any(r["id"] == "#2" for r in gitclaim.load_unaccepted(tmp_path))


def test_offer_then_ack_accepts_second_shop_cannot_take(tmp_path):
    gitclaim.enqueue_unaccepted(
        tmp_path,
        gitclaim.GitClaim(
            "SimonBarnett/skills-visionary", "FR", "#19", "issues", "opened", ""
        ),
    )
    st, job = gitclaim.offer_top(tmp_path, "marchhare-34992", "#marchhare")
    assert st == "ok" and job["id"] == "#19"
    assert job["offered_to"] == "marchhare-34992"
    # still unaccepted
    assert len(gitclaim.load_unaccepted(tmp_path)) == 1
    st2, job2 = gitclaim.accept_offered(tmp_path, "marchhare-34992", "#marchhare")
    assert st2 == "ok" and job2["id"] == "#19"
    assert gitclaim.load_unaccepted(tmp_path) == []
    assert gitclaim.load_accepted(tmp_path)[0]["nick"] == "marchhare-34992"
    # second shop: empty
    st3, _ = gitclaim.offer_top(tmp_path, "w-fl-1", "#flamingo")
    assert st3 == "empty"


def test_resync_adds_open_and_drops_superseded(tmp_path):
    # stale FR that PR closes
    gitclaim.enqueue_unaccepted(
        tmp_path,
        gitclaim.GitClaim("SimonBarnett/AgentMonitor", "FR", "#88", "issues", "opened", ""),
    )
    gitclaim.enqueue_unaccepted(
        tmp_path,
        gitclaim.GitClaim("SimonBarnett/AgentMonitor", "FR", "#99", "issues", "opened", ""),
    )

    def fetch(url: str):
        if "/pulls?" in url:
            return [
                {
                    "number": 87,
                    "title": "fix",
                    "body": "Closes #88",
                }
            ]
        if "/issues?" in url:
            return [
                {"number": 88, "title": "old fr", "pull_request": None},
                {"number": 99, "title": "still open"},
                {"number": 87, "title": "pr issue", "pull_request": {}},
            ]
        raise AssertionError(url)

    out = gitclaim.resync_from_github(
        tmp_path, ["SimonBarnett/AgentMonitor"], fetch_json=fetch
    )
    assert out["ok"] is True
    rows = gitclaim.load_unaccepted(tmp_path)
    kinds = {(r["id"], r["task"]) for r in rows}
    assert ("#87", "MRB") in kinds
    assert ("#99", "FR") in kinds
    assert ("#88", "FR") not in kinds


def test_e2e_scripts_only_bored_offer_ack(tmp_path, monkeypatch):
    """No LLM: enqueue FR, offer via offer_top, ACK accept_offered."""
    claim = gitclaim.claim_from_payload(
        "issues",
        {
            "action": "opened",
            "issue": {"number": 42, "title": "ship"},
            "repository": {"full_name": "SimonBarnett/agentic_irc"},
        },
    )
    assert claim and claim.task == "FR"
    assert gitclaim.enqueue_unaccepted(tmp_path, claim) == "added"
    # simulate !BORED gate ok
    monkeypatch.setattr(gitclaim, "last_worker_activity", lambda *a, **k: None)
    monkeypatch.setattr(gitclaim, "worker_working_on", lambda *a, **k: "")
    assert gitclaim.bored_gate(tmp_path, "w-mh-3", "#marchhare", 1e9) == "ok"
    st, job = gitclaim.offer_top(tmp_path, "w-mh-3", "#marchhare")
    assert st == "ok"
    assert gitclaim.parse_worker_ack("w-mh-3: ACK starting")
    st2, acc = gitclaim.accept_offered(tmp_path, "w-mh-3", "#marchhare")
    assert st2 == "ok" and acc["id"] == "#42"
    assert gitclaim.load_unaccepted(tmp_path) == []
