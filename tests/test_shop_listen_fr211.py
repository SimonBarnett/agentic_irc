"""FR #211: shop ACK/DONE → queue + activity webhook (local digest, no live IRC)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bobreport
import gitclaim
import shop_listen


def test_parse_ack_done_grammar():
    a = shop_listen.parse_shop_job_line("ACK FR SimonBarnett/agentic_irc#206 secret filter")
    assert a and a.verb == "ACK" and a.task == "FR" and a.repo == "SimonBarnett/agentic_irc"
    assert a.id == "#206" and "secret filter" in a.title
    d = shop_listen.parse_shop_job_line(
        "DONE MRB SimonBarnett/skills-visionary#18 PASS merged https://github.com/x/y/pull/18"
    )
    assert d and d.verb == "DONE" and "PASS" in d.result and d.url.endswith("/pull/18")
    g = shop_listen.parse_shop_job_line("GIVEUP FR SimonBarnett/x#1")
    assert g and g.verb == "GIVEUP"
    assert shop_listen.parse_shop_job_line("hello world") is None
    assert shop_listen.parse_shop_job_line("ACK not-a-job") is None


def test_activity_description_shape():
    line = shop_listen.ShopJobLine("ACK", "FR", "SimonBarnett/agentic_irc", "#206", title="fix filter")
    assert shop_listen.activity_description(line) == "FR SimonBarnett/agentic_irc#206 fix filter"


def test_ack_moves_queue_and_posts_busy(tmp_path):
    home = tmp_path
    claim = gitclaim.GitClaim(
        "SimonBarnett/agentic_irc",
        "FR",
        "#206",
        "issues",
        "opened",
        "GIT issues SimonBarnett/agentic_irc opened #206 fix filter by simon",
    )
    assert gitclaim.enqueue_unaccepted(home, claim) == "added"
    posts: list[dict] = []

    def post_fn(payload: dict) -> int:
        posts.append(payload)
        bobreport.apply_callback(home, payload, "Jeeves")
        return 204

    r = shop_listen.handle_shop_worker_line(
        home,
        nick="marchhare-34992",
        channel="#marchhare",
        body="ACK FR SimonBarnett/agentic_irc#206 fix filter",
        post_fn=post_fn,
    )
    assert r["handled"] and r["status"] == "ok"
    assert r["activity"].startswith("FR SimonBarnett/agentic_irc#206")
    assert gitclaim.load_unaccepted(home) == []
    acc = gitclaim.load_accepted(home)
    assert len(acc) == 1 and acc[0]["nick"] == "marchhare-34992"
    assert posts and posts[0]["state"] == "running"
    assert "FR SimonBarnett/agentic_irc#206" in posts[0]["working_on"]
    assert posts[0]["machine"] == "marchhare" and posts[0]["pid"] == 34992
    # digest workers show busy
    doc = bobreport.load_digest(home)
    w = doc["machines"]["marchhare"]["workers"]["34992"]
    assert w["working_on"].startswith("FR SimonBarnett/agentic_irc#206")
    assert w["state"] != "idle" or w["working_on"]  # running with description


def test_done_clears_activity_and_supersedes_fr_to_mrb(tmp_path):
    home = tmp_path
    gitclaim.enqueue_unaccepted(
        home,
        gitclaim.GitClaim("SimonBarnett/x", "FR", "#1", "issues", "opened", ""),
    )
    posts: list[dict] = []

    def post_fn(payload: dict) -> int:
        posts.append(dict(payload))
        bobreport.apply_callback(home, payload, "Jeeves")
        return 204

    shop_listen.handle_shop_worker_line(
        home,
        nick="marchhare-42",
        channel="#marchhare",
        body="ACK FR SimonBarnett/x#1",
        post_fn=post_fn,
    )
    r = shop_listen.handle_shop_worker_line(
        home,
        nick="marchhare-42",
        channel="#marchhare",
        body="DONE FR SimonBarnett/x#1 PR https://github.com/SimonBarnett/x/pull/9",
        post_fn=post_fn,
    )
    assert r["status"] == "ok"
    assert r["activity"] == ""
    assert posts[-1]["state"] == "idle"
    assert posts[-1].get("working_on") == ""
    # FR done → MRB #9 unaccepted
    un = gitclaim.load_unaccepted(home)
    assert any(row.get("task") == "MRB" and row.get("id") == "#9" for row in un)
    doc = bobreport.load_digest(home)
    w = doc["machines"]["marchhare"]["workers"]["42"]
    assert w.get("state") == "idle" or w.get("working_on") == ""


def test_ignore_bob_and_wrong_channel(tmp_path):
    gitclaim.enqueue_unaccepted(
        tmp_path,
        gitclaim.GitClaim("SimonBarnett/x", "MRB", "#3", "pull_request", "opened", ""),
    )
    r = shop_listen.handle_shop_worker_line(
        tmp_path,
        nick="bob-marchhare",
        channel="#marchhare",
        body="ACK MRB SimonBarnett/x#3",
    )
    assert not r["handled"]
    r2 = shop_listen.handle_shop_worker_line(
        tmp_path,
        nick="marchhare-1",
        channel="#flamingo",
        body="ACK MRB SimonBarnett/x#3",
    )
    assert not r2["handled"]
    assert len(gitclaim.load_unaccepted(tmp_path)) == 1


def test_quit_returns_job_and_idles(tmp_path):
    home = tmp_path
    gitclaim.enqueue_unaccepted(
        home,
        gitclaim.GitClaim("SimonBarnett/x", "FR", "#7", "issues", "opened", ""),
    )
    posts: list[dict] = []

    def post_fn(payload: dict) -> int:
        posts.append(dict(payload))
        bobreport.apply_callback(home, payload, "Jeeves")
        return 204

    shop_listen.handle_shop_worker_line(
        home,
        nick="ionos-99",
        channel="#ionos",
        body="ACK FR SimonBarnett/x#7",
        post_fn=post_fn,
    )
    assert gitclaim.load_accepted(home)
    q = shop_listen.handle_shop_worker_quit(home, nick="ionos-99", post_fn=post_fn)
    assert q["handled"] and q.get("returned", 0) >= 1
    assert posts[-1]["state"] == "idle"
    assert any(r.get("id") == "#7" for r in gitclaim.load_unaccepted(home))


def test_duplicate_ack_idempotent(tmp_path):
    home = tmp_path
    gitclaim.enqueue_unaccepted(
        home,
        gitclaim.GitClaim("SimonBarnett/x", "MRB", "#5", "pull_request", "opened", ""),
    )
    posts: list[dict] = []

    def post_fn(payload: dict) -> int:
        posts.append(payload)
        bobreport.apply_callback(home, payload, "Jeeves")
        return 204

    r1 = shop_listen.handle_shop_worker_line(
        home,
        nick="flamingo-8",
        channel="#flamingo",
        body="ACK MRB SimonBarnett/x#5",
        post_fn=post_fn,
    )
    r2 = shop_listen.handle_shop_worker_line(
        home,
        nick="flamingo-8",
        channel="#flamingo",
        body="ACK MRB SimonBarnett/x#5",
        post_fn=post_fn,
    )
    assert r1["status"] == "ok"
    assert r2["status"] == "duplicate"
    assert len(gitclaim.load_accepted(home)) == 1


def test_irc_agent_wires_shop_listen():
    src = (Path(__file__).resolve().parents[1] / "scripts" / "irc_agent.py").read_text(
        encoding="utf-8"
    )
    assert "import shop_listen" in src
    assert "_maybe_shop_listen" in src
    assert "handle_shop_worker_quit" in src
    assert "Never PRIVMSG the shop channel" in src or "no channel reply" in src.lower()
