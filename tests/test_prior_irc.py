"""Deterministic prior cleanup. No live IRC. No process kills of this machine."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import irc_agent
import irc_listen
import prior_irc
import start_worker_irc_agent


def _agent(nick: str, home: str, *, extra: str = "") -> str:
    return (
        f"python -u scripts/irc_agent.py --host irc.ntsa.uk --port 6697 "
        f"--nick {nick} --home {home} {extra}"
    ).strip()


def _listen(home: str) -> str:
    return f"python -u scripts/irc_listen.py --home {home}"


def test_second_start_keeps_only_self_same_nick():
    """A hung prior of the same nick is selected; the process about to connect is not."""
    home = "/var/ear/.agentic-irc-bobiverse"
    nick = "bob-flamingo"
    cmd = _agent(nick, home)
    procs = [(10, cmd), (11, cmd), (99, cmd)]
    victims = prior_irc.select_victims(procs, nick, home, keep_pids={99})
    assert victims == [(10, "irc_agent"), (11, "irc_agent")]
    state = list(procs)

    def lister():
        return list(state)

    def killer(pid: int) -> bool:
        state[:] = [(p, c) for p, c in state if p != pid]
        return True

    result = prior_irc.clean_priors(
        nick,
        home,
        self_pid=99,
        wait_s=0,
        list_processes=lister,
        killer=killer,
        sleeper=lambda _s: None,
    )
    assert result.scanned
    assert [pid for pid, _ in result.killed] == [10, 11]
    assert [pid for pid, _ in state] == [99]
    again = prior_irc.select_victims(state, nick, home, keep_pids={99})
    assert again == []


def test_bob_builder_kills_cursor_listen_pile_not_cursor2_or_workers():
    home = "/var/ear/.agentic-irc-bobiverse"
    cursor = "/var/ear/.agentic-irc-cursor"
    cursor2 = "/var/ear/.agentic-irc-cursor-2"
    worker_home = home + "/workers/flamingo/4412"
    procs = [(1000 + i, _listen(cursor)) for i in range(60)]
    procs.append((2000, _listen(cursor2)))
    procs.append((2001, _listen(home)))
    procs.append((3000, _agent("w-fl-4412", worker_home)))
    procs.append((3001, _agent("flamingo-22400", cursor)))
    procs.append((3002, _agent("bob", "/var/ear/other")))
    procs.append((3003, _agent("bob-ionos", "/var/ear/ionos-home")))
    victims = dict(
        prior_irc.select_victims(procs, "bob-flamingo", home, keep_pids={1})
    )
    assert len([pid for pid in victims if 1000 <= pid < 1060]) == 60
    assert victims[2001] == "irc_listen"
    assert 2000 not in victims
    assert 3000 not in victims
    assert 3001 not in victims
    assert victims[3002] == "irc_agent"
    assert 3003 not in victims


def test_talk_seat_does_not_sweep_cursor_or_bare_bob():
    home = "/var/ear/.agentic-irc-cursor-2"
    procs = [
        (11, _listen("/var/ear/.agentic-irc-cursor")),
        (2, _agent("bob", "/tmp/bob")),
        (3, _agent("bob-flamingo", "/var/ear/.agentic-irc-bobiverse")),
        (4, _listen(home)),
        (5, _agent("flamingo-9", home)),
        (6, _agent("flamingo-9", "/tmp/other-home")),
    ]
    victims = dict(
        prior_irc.select_victims(procs, "flamingo-9", home, keep_pids=set())
    )
    assert 11 not in victims
    assert 2 not in victims
    assert 3 not in victims
    assert victims[4] == "irc_listen"
    assert victims[5] == "irc_agent"
    assert victims[6] == "irc_agent"


def test_same_home_different_nick_is_killed_child_home_is_not():
    home = "/var/ear/.agentic-irc-bobiverse"
    procs = [
        (7, _agent("Jeeves", home)),
        (8, _agent("w-io-9", home + "/workers/ionos/9")),
    ]
    victims = dict(prior_irc.select_victims(procs, "bob-ionos", home, keep_pids=set()))
    assert victims[7] == "irc_agent"
    assert 8 not in victims


def test_nick_match_is_exact():
    home = "/tmp/h"
    procs = [
        (1, _agent("bob-flamingo2", home + "-other")),
        (2, "--nick=bob-flamingo"),
        (3, "python irc_agent.py --nick bob-flamingo --home /tmp/other"),
        (4, "python irc_agent.py --nick=bob-flamingo --home=/tmp/other"),
    ]
    # pid 2 has no script boundary match (flag only) — not a victim
    victims = prior_irc.select_victims(procs, "bob-flamingo", home, keep_pids=set())
    assert [pid for pid, _ in victims] == [3, 4]


def test_quoted_home_and_trailing_slash():
    procs = [
        (5, 'python irc_agent.py --nick other --home "/tmp/ear/"'),
        (6, r"python irc_listen.py --home /tmp/ear"),
    ]
    victims = prior_irc.select_victims(procs, "bob-flamingo", "/tmp/ear", keep_pids=set())
    assert victims == [(5, "irc_agent"), (6, "irc_listen")]


def test_cursor_ghost_basename_is_exact():
    assert prior_irc.is_cursor_ghost_home(r"C:\Users\A\.agentic-irc-cursor")
    assert prior_irc.is_cursor_ghost_home("/home/a/.agentic-irc-cursor/")
    assert not prior_irc.is_cursor_ghost_home("/home/a/.agentic-irc-cursor-2")
    assert not prior_irc.is_cursor_ghost_home("/home/a/.agentic-irc-cursor-extra")
    assert prior_irc.normalize_home(r"C:\Users\A\Ear", casefold=True) == prior_irc.normalize_home(
        "c:/users/a/ear", casefold=True
    )


def test_both_script_names_on_one_command_line_are_skipped():
    cmdline = "python irc_agent.py irc_listen.py --nick bob-flamingo --home /tmp/h"
    assert prior_irc.script_kind(cmdline) is None
    assert prior_irc.select_victims([(4, cmdline)], "bob-flamingo", "/tmp/h") == []


def test_no_wait_when_nothing_matches():
    slept: list[float] = []
    killed: list[int] = []
    result = prior_irc.clean_priors(
        "bob-flamingo",
        "/tmp/empty",
        self_pid=50,
        wait_s=3,
        list_processes=lambda: [(50, _agent("bob-flamingo", "/tmp/empty"))],
        killer=lambda pid: killed.append(pid) or True,
        sleeper=slept.append,
    )
    assert result.killed == []
    assert killed == []
    assert slept == []
    assert result.wait_s == 0


def test_straggler_gets_a_second_pass_then_stops():
    home = "/tmp/h"
    nick = "bob-marchhare"
    rounds = {"n": 0}

    def lister():
        rounds["n"] += 1
        if rounds["n"] == 1:
            return [(2, _agent(nick, home)), (3, _agent(nick, home))]
        if rounds["n"] == 2:
            return [(3, _agent(nick, home))]
        return []

    slept: list[float] = []
    result = prior_irc.clean_priors(
        nick,
        home,
        self_pid=1,
        wait_s=0,
        list_processes=lister,
        killer=lambda _pid: True,
        sleeper=slept.append,
    )
    pids = [pid for pid, _ in result.killed]
    assert result.rounds == 2
    assert pids[0] == 2
    assert 3 in pids
    assert slept == []


def test_wait_is_clamped():
    assert prior_irc.resolve_wait_s(0) == 0
    assert prior_irc.resolve_wait_s(1) == 2
    assert prior_irc.resolve_wait_s(3) == 3
    assert prior_irc.resolve_wait_s(9) == 5


def test_dry_run_prints_pids_not_command_lines(capsys):
    secret_home = "/tmp/ear"
    cmdline = _agent("bob-flamingo", secret_home) + " --password SUPERSECRET"
    result = prior_irc.clean_priors(
        "bob-flamingo",
        secret_home,
        self_pid=0,
        dry_run=True,
        list_processes=lambda: [(42, cmdline)],
        killer=lambda _pid: (_ for _ in ()).throw(AssertionError("dry-run must not kill")),
    )
    out = capsys.readouterr().out
    assert "pid=42" in out
    assert "kind=irc_agent" in out
    assert "SUPERSECRET" not in out
    assert "irc_agent.py" not in out
    assert "--password" not in out
    assert result.would_kill == [(42, "irc_agent")]


def test_scan_failure_does_not_connect(monkeypatch):
    def boom():
        raise OSError("ps failed")

    result = prior_irc.clean_priors(
        "bob-ionos",
        "/tmp/h",
        self_pid=1,
        list_processes=boom,
    )
    assert result.scanned is False

    calls: list[tuple] = []

    def fake_clean(nick, home, **kwargs):
        calls.append((nick, home, kwargs))
        return prior_irc.PriorCleanResult(scanned=False)

    monkeypatch.setattr(prior_irc, "clean_priors", fake_clean)
    with pytest.raises(SystemExit) as exc:
        irc_agent.clean_crashed_priors("bob-flamingo", "/tmp/h", once=False)
    assert exc.value.code == 1
    assert calls and calls[0][0] == "bob-flamingo"


def test_agent_sweeps_listens_only_for_bob_builder(monkeypatch):
    seen: list[bool] = []

    def fake_clean(nick, home, **kwargs):
        seen.append(bool(kwargs.get("include_listens")))
        return prior_irc.PriorCleanResult(scanned=True)

    monkeypatch.setattr(prior_irc, "clean_priors", fake_clean)
    irc_agent.clean_crashed_priors("flamingo-22400", "/tmp/h", once=False)
    irc_agent.clean_crashed_priors("bob-flamingo", "/tmp/h", once=False)
    assert seen == [False, True]


def test_once_and_env_skip_prior_clean(monkeypatch):
    monkeypatch.setattr(
        prior_irc,
        "clean_priors",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must skip")),
    )
    irc_agent.clean_crashed_priors("bob-flamingo", "/tmp/h", once=True)
    monkeypatch.setenv("AGENTIC_IRC_SKIP_PRIOR_CLEAN", "1")
    irc_agent.clean_crashed_priors("bob-flamingo", "/tmp/h", once=False)


def test_irc_agent_main_calls_clean_before_client():
    src = (Path(__file__).resolve().parents[1] / "scripts" / "irc_agent.py").read_text(
        encoding="utf-8"
    )
    assert src.index("clean_crashed_priors(") < src.index("c = Client(args)")


def test_worker_spawn_cleans_then_starts(tmp_path, monkeypatch):
    calls: list[tuple] = []

    def fake_clean(nick, home, **kwargs):
        calls.append((nick, home))
        return prior_irc.PriorCleanResult(scanned=True)

    monkeypatch.setattr(start_worker_irc_agent.prior_irc, "clean_priors", fake_clean)
    popen = monkeypatch.setattr(
        start_worker_irc_agent.subprocess,
        "Popen",
        lambda *a, **k: type("P", (), {"pid": 1})(),
    )
    del popen
    rc = start_worker_irc_agent.main(
        ["--fleet-home", str(tmp_path), "--machine-id", "ionos", "--pid", "4412"]
    )
    assert rc == 0
    assert calls == [("w-io-4412", str(tmp_path / "workers" / "ionos" / "4412"))]


def test_worker_dry_run_does_not_clean(tmp_path, monkeypatch):
    monkeypatch.setattr(
        start_worker_irc_agent.prior_irc,
        "clean_priors",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("dry-run must not clean")),
    )
    rc = start_worker_irc_agent.main(
        [
            "--fleet-home",
            str(tmp_path),
            "--machine-id",
            "ionos",
            "--pid",
            "4412",
            "--dry-run",
        ]
    )
    assert rc == 0


def test_listen_stdout_log_is_the_childs_file(tmp_path):
    home = tmp_path / "seat"
    home.mkdir()
    (home / "irc.log").write_text(
        ":bob-ionos!~u@x PRIVMSG #bobiverse :ping\n",
        encoding="utf-8",
    )
    out = tmp_path / "listen.stdout.log"
    err = tmp_path / "listen.stderr.log"
    rc = irc_listen.main(
        [
            "--home",
            str(home),
            "--once",
            "--stdout-log",
            str(out),
            "--stderr-log",
            str(err),
        ]
    )
    assert rc == 0
    assert "FROM bob-ionos #bobiverse ping" in out.read_text(encoding="utf-8")


def test_start_scripts_document_the_rules():
    root = Path(__file__).resolve().parents[1]
    ear = (root / "scripts" / "Start-BobEar.ps1").read_text(encoding="utf-8")
    doc = (root / "docs" / "prior-irc-clean.md").read_text(encoding="utf-8")
    assert "prior_irc.py" in ear
    assert "Start-HiddenPython" in ear
    assert "AGENTIC_IRC_PASSWORD" in ear
    for line in ear.splitlines():
        if line.lstrip().startswith("#"):
            continue
        assert "WindowStyle Hidden" not in line
        assert "Start-Process" not in line
    assert ".agentic-irc-cursor" in doc
    assert "bob-flamingo_1" in doc or "suffixed nick" in doc
    assert "--dry-run" in doc

def test_nick_match_is_case_insensitive():
    """Rules say --nick equals N exact, case-insensitive. pid<=1 is never a victim."""
    home = "/tmp/h"
    procs = [
        (10, _agent("Bob-Flamingo", "/tmp/other")),
        (20, _agent("BOB-FLAMINGO", home)),
        (30, _agent("bob-flamingo2", "/tmp/x")),
    ]
    victims = prior_irc.select_victims(procs, "bob-flamingo", home, keep_pids=set())
    assert [pid for pid, _ in victims] == [10, 20]


def test_wait_runs_only_after_a_kill():
    slept: list[float] = []
    home = "/tmp/h"
    nick = "bob-flamingo"
    state = [(10, _agent(nick, home)), (99, _agent(nick, home))]

    def lister():
        return list(state)

    def killer(pid: int) -> bool:
        state[:] = [(p, c) for p, c in state if p != pid]
        return True

    result = prior_irc.clean_priors(
        nick,
        home,
        self_pid=99,
        wait_s=3,
        list_processes=lister,
        killer=killer,
        sleeper=slept.append,
    )
    assert [pid for pid, _ in result.killed] == [10]
    assert slept == [3.0]
    assert result.wait_s == 3.0


def test_include_listens_false_skips_cursor_and_home_listens():
    home = "/var/ear/.agentic-irc-bobiverse"
    cursor = "/var/ear/.agentic-irc-cursor"
    procs = [
        (1, _listen(cursor)),
        (2, _listen(home)),
        (3, _agent("bob-flamingo", home)),
        (4, _agent("bob", "/tmp/ghost")),
    ]
    victims = dict(
        prior_irc.select_victims(
            procs, "bob-flamingo", home, keep_pids={99}, include_listens=False
        )
    )
    assert 1 not in victims
    assert 2 not in victims
    assert victims[3] == "irc_agent"
    assert victims[4] == "irc_agent"


def test_env_wait_is_clamped(monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_PRIOR_WAIT_S", "1")
    assert prior_irc.resolve_wait_s(None) == 2.0
    monkeypatch.setenv("AGENTIC_IRC_PRIOR_WAIT_S", "99")
    assert prior_irc.resolve_wait_s(None) == 5.0
    monkeypatch.setenv("AGENTIC_IRC_PRIOR_WAIT_S", "not-a-number")
    assert prior_irc.resolve_wait_s(None) == prior_irc.WAIT_DEFAULT_S
    monkeypatch.delenv("AGENTIC_IRC_PRIOR_WAIT_S", raising=False)
    assert prior_irc.resolve_wait_s(None) == prior_irc.WAIT_DEFAULT_S


def test_keep_pids_survive_clean_priors():
    home = "/tmp/h"
    nick = "bob-marchhare"
    state = [
        (10, _agent(nick, home)),
        (11, _agent(nick, home)),
        (12, _agent(nick, home)),
    ]
    killed: list[int] = []

    def killer(pid: int) -> bool:
        killed.append(pid)
        state[:] = [(p, c) for p, c in state if p != pid]
        return True

    result = prior_irc.clean_priors(
        nick,
        home,
        self_pid=12,
        keep_pids={11},
        wait_s=0,
        list_processes=lambda: list(state),
        killer=killer,
        sleeper=lambda _s: None,
    )
    assert killed == [10]
    assert [pid for pid, _ in state] == [11, 12]
    assert result.killed == [(10, "irc_agent")]


def test_bob_alone_is_not_a_builder_nick():
    assert prior_irc.is_bob_builder_nick("bob-flamingo")
    assert prior_irc.is_bob_builder_nick("bob-ionos")
    assert not prior_irc.is_bob_builder_nick("bob")
    assert not prior_irc.is_bob_builder_nick("flamingo")
    assert not prior_irc.is_bob_builder_nick("bobflamingo")


def test_start_talk_seat_avoids_windowstyle_hidden():
    root = Path(__file__).resolve().parents[1]
    talk = (root / "scripts" / "Start-TalkSeat.ps1").read_text(encoding="utf-8")
    irc = (root / "scripts" / "IrcProcess.ps1").read_text(encoding="utf-8")
    assert "Invoke-PriorIrcClean" in talk
    assert "Start-HiddenPython" in talk
    assert "CreateNoWindow" in irc
    for path_text in (talk, irc):
        for line in path_text.splitlines():
            if line.lstrip().startswith("#"):
                continue
            assert "WindowStyle Hidden" not in line
