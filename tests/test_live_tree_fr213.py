"""FR #213: live service tree must not be checked out/stashed by MRB; backoff grows."""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import live_tree_guard  # noqa: E402
import monitor_restart_backoff as mrb  # noqa: E402
import temp_git_worktree as tw  # noqa: E402


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )


@pytest.fixture
def bare_live_repo(tmp_path: Path) -> Path:
    """Small git repo standing in for D:\\ai\\agentic_irc service tree."""
    live = tmp_path / "live-service"
    live.mkdir()
    _git(live, "init")
    _git(live, "config", "user.email", "fr213@test")
    _git(live, "config", "user.name", "fr213")
    (live / "README").write_text("main\n", encoding="utf-8")
    _git(live, "add", "README")
    _git(live, "commit", "-m", "init")
    # ensure branch name main
    _git(live, "branch", "-M", "main")
    _git(live, "checkout", "-b", "feature/mrb-target")
    (live / "README").write_text("feature\n", encoding="utf-8")
    _git(live, "add", "README")
    _git(live, "commit", "-m", "feature")
    _git(live, "checkout", "main")
    return live


def test_mrb_flow_leaves_live_head_and_status_unchanged(bare_live_repo: Path, tmp_path: Path):
    """Acceptance: MRB checkout via worktree does not change live rev-parse/status."""
    before_branch = _git(bare_live_repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    before_status = _git(bare_live_repo, "status", "--porcelain").stdout
    before_head = _git(bare_live_repo, "rev-parse", "HEAD").stdout.strip()
    assert before_branch == "main"

    result = tw.run_mrb_checkout_flow(
        bare_live_repo,
        "feature/mrb-target",
        base_dir=tmp_path / "wt",
        work_fn=lambda p: (p / "touched.txt").write_text("x", encoding="utf-8"),
    )
    assert result["live_unchanged"] is True
    after_branch = _git(bare_live_repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    after_status = _git(bare_live_repo, "status", "--porcelain").stdout
    after_head = _git(bare_live_repo, "rev-parse", "HEAD").stdout.strip()
    assert after_branch == before_branch == "main"
    assert after_status == before_status
    assert after_head == before_head
    # worktree removed
    assert not Path(str(result["worktree"])).exists()


def test_assert_refuses_mutation_on_protected_path(tmp_path: Path, monkeypatch):
    live = tmp_path / "ai" / "agentic_irc"
    live.mkdir(parents=True)
    monkeypatch.setenv("AGENTIC_IRC_SERVICE_TREE", str(live))
    with pytest.raises(tw.LiveTreeMutationError):
        tw.assert_not_live_mutation(live, "git checkout")


def test_guard_warns_off_main_and_writes_report(bare_live_repo: Path, tmp_path: Path):
    _git(bare_live_repo, "checkout", "feature/mrb-target")
    home = tmp_path / "home"
    home.mkdir()
    logs: list[str] = []
    snap = live_tree_guard.check_and_report(
        tree=bare_live_repo,
        home=home,
        role="irc_agent",
        log=logs.append,
        mark_start=True,
    )
    assert snap.ok is False
    assert snap.branch == "feature/mrb-target"
    assert any("expected 'main'" in w for w in snap.warnings)
    assert any("WARN live-tree" in x for x in logs)
    report = home / live_tree_guard.WARN_REPORT
    assert report.is_file()
    assert (home / live_tree_guard.START_MARKER).is_file()


def test_guard_warns_stash_newer_than_start(bare_live_repo: Path, tmp_path: Path):
    home = tmp_path / "home2"
    home.mkdir()
    # mark start in the past
    past = time.time() - 3600
    live_tree_guard.write_start_marker(home, when=past)
    (bare_live_repo / "dirty.txt").write_text("d", encoding="utf-8")
    _git(bare_live_repo, "add", "dirty.txt")
    _git(bare_live_repo, "stash", "push", "-m", "mrb-dirty")
    snap = live_tree_guard.inspect_live_tree(bare_live_repo, home=home)
    assert snap.newest_stash_unix is not None
    assert snap.newest_stash_unix > past
    assert any("stash newer" in w for w in snap.warnings)
    assert snap.ok is False


def test_restart_backoff_grows_after_n_consecutive_fast_exits(tmp_path: Path, monkeypatch):
    """Acceptance: delay grows after N consecutive fast exits and caps."""
    monkeypatch.setenv("AGENTIC_IRC_MONITOR_BACKOFF_BASE_S", "2")
    monkeypatch.setenv("AGENTIC_IRC_MONITOR_BACKOFF_CAP_S", "64")
    monkeypatch.setenv("AGENTIC_IRC_MONITOR_FAST_EXIT_S", "30")
    home = tmp_path / "mon"
    home.mkdir()
    delays = []
    t0 = 1_000_000.0
    for i in range(1, 8):
        mrb.note_start(home, now=t0 + i * 100)
        # exit 5s later = fast
        st, delay = mrb.note_exit(home, now=t0 + i * 100 + 5.0, fast_window_s=30.0)
        delays.append(delay)
        assert st.consecutive_fast == i
    assert delays[0] == 2.0
    assert delays[1] == 4.0
    assert delays[2] == 8.0
    assert all(b >= a for a, b in zip(delays, delays[1:]))
    assert delays[-1] == 64.0  # capped
    # slow exit resets
    mrb.note_start(home, now=t0 + 10_000)
    st2, d2 = mrb.note_exit(home, now=t0 + 10_000 + 120.0, fast_window_s=30.0)
    assert st2.consecutive_fast == 0
    assert d2 == 0.0
    mrb.note_healthy(home)
    assert mrb.load_state(home).consecutive_fast == 0


def test_delay_after_fast_exits_pure():
    d = [mrb.delay_after_fast_exits(n, base=2.0, cap=300.0) for n in range(0, 12)]
    assert d[0] == 0.0
    assert d[1] == 2.0
    assert d[2] == 4.0
    assert max(d) == 300.0


def test_irc_agent_wires_live_tree_guard():
    src = (ROOT / "scripts" / "irc_agent.py").read_text(encoding="utf-8")
    assert "live_tree_guard" in src
    assert "check_and_report" in src


def test_watch_agent_health_wires_backoff():
    src = (ROOT / "scripts" / "Watch-AgentHealth.ps1").read_text(encoding="utf-8")
    assert "monitor-wait" in src
    assert "monitor-note-exit" in src
    assert "live-tree-check" in src
    assert "monitor-note-healthy" in src
