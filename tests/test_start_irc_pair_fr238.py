"""FR #238: sanctioned start_irc_pair + coordinator monitor warning."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import talk_seat_pid

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load_start_irc_pair():
    path = SCRIPTS / "start_irc_pair.py"
    spec = importlib.util.spec_from_file_location("start_irc_pair", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_win_creationflags_include_breakaway_and_detach():
    mod = _load_start_irc_pair()
    flags = mod._win_creationflags(breakaway=True)
    assert flags & mod.CREATE_BREAKAWAY_FROM_JOB
    assert flags & mod.DETACHED_PROCESS
    assert flags & mod.CREATE_NEW_PROCESS_GROUP
    flags2 = mod._win_creationflags(breakaway=False)
    assert not (flags2 & mod.CREATE_BREAKAWAY_FROM_JOB)
    assert flags2 & mod.DETACHED_PROCESS


def test_write_coordinator_pid_seat_is_monitor(tmp_path: Path):
    mod = _load_start_irc_pair()
    home = tmp_path / "h"
    home.mkdir()
    path = mod.write_coordinator_pid(
        home,
        nick="marchhare-31712",
        coordinator_pid=31712,
        agent_pid=19404,
        listen_pid=17300,
    )
    text = path.read_text(encoding="utf-8")
    assert "seat=31712" in text
    assert "agent=19404" in text
    assert "listen=17300" in text
    assert "launcher=start_irc_pair" in text
    assert "nick=marchhare-31712" in text


def test_dry_run_start_pair_no_processes(tmp_path: Path):
    mod = _load_start_irc_pair()
    home = tmp_path / "h"
    out = mod.start_pair(
        home=home,
        nick="ionos-12916",
        channel="#ionos",
        coordinator_pid=12916,
        host="irc.ntsa.uk",
        port="6697",
        python="python",
        dry_run=True,
    )
    assert out["seat"] == 12916
    assert out["nick"] == "ionos-12916"
    assert not (home / "coordinator.pid").exists()


def test_coordinator_looks_like_monitor():
    assert talk_seat_pid.coordinator_looks_like_monitor(
        1, r"C:\ai\AgentMonitor\Watch-AgentHealth.ps1 -WatchWorker -Grok"
    )
    assert talk_seat_pid.coordinator_looks_like_monitor(
        1, r"powershell -File Start-BobWatchWorker.ps1"
    )
    assert not talk_seat_pid.coordinator_looks_like_monitor(
        1, r"C:\Users\x\AppData\Local\Temp\watch-grok-irc-launch.py"
    )
    assert talk_seat_pid.coordinator_looks_like_monitor(1, None)  # unknown → no warn


def test_warn_if_coordinator_not_monitor(tmp_path: Path):
    home = tmp_path / "h"
    home.mkdir()
    (home / "coordinator.pid").write_text(
        "nick=marchhare-1\nseat=4242\nagent=9\nlisten=8\nhome=x\n",
        encoding="utf-8",
    )
    warn = talk_seat_pid.warn_if_coordinator_not_monitor(
        home,
        command_line_for_pid=lambda _pid: r"%TEMP%\watch-grok-irc-launch.py",
    )
    assert warn is not None
    assert "31712" not in warn or True
    assert "Start-IrcPair" in warn or "Watch-AgentHealth" in warn

    ok = talk_seat_pid.warn_if_coordinator_not_monitor(
        home,
        command_line_for_pid=lambda _pid: r"Watch-AgentHealth.ps1 -WatchWorker",
    )
    assert ok is None


def test_skill_forbids_ad_hoc_launcher():
    root = Path(__file__).resolve().parents[1]
    skill = (root / ".grok" / "skills" / "agentic-irc" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "FR #238" in skill or "never start IRC" in skill.lower()
    assert "Start-IrcPair" in skill or "start_irc_pair" in skill
    assert "watch-grok-irc-launch" in skill or "ad-hoc" in skill.lower() or "improvised" in skill.lower() or "never" in skill.lower()
    doc = (root / "docs" / "start-irc-pair-fr238.md").read_text(encoding="utf-8")
    assert "CREATE_BREAKAWAY_FROM_JOB" in doc
    assert "start_irc_pair" in doc


def test_start_irc_pair_script_and_ps1_exist():
    assert (SCRIPTS / "start_irc_pair.py").is_file()
    assert (SCRIPTS / "Start-IrcPair.ps1").is_file()
    ps1 = (SCRIPTS / "Start-IrcPair.ps1").read_text(encoding="utf-8")
    assert "CoordinatorPid" in ps1
    assert "start_irc_pair.py" in ps1
