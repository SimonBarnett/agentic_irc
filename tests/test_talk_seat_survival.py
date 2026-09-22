from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import talk_seat_pid as tsp


def test_home_bind_refuses_live_other_nick():
    coord = {"nick": "flamingo-100", "seat": "100"}
    err = tsp.home_bind_refusal(
        coord,
        "flamingo-200",
        live_agent_nick="flamingo-100",
        has_live_listen=False,
    )
    assert err and "flamingo-100" in err and "flamingo-200" in err
    assert "IrcHome" in err


def test_home_bind_refuses_listen_without_agent_when_coord_foreign():
    coord = {"nick": "marchhare-20280", "seat": "20280"}
    err = tsp.home_bind_refusal(
        coord,
        "marchhare-30303",
        live_agent_nick=None,
        has_live_listen=True,
    )
    assert err and "marchhare-20280" in err


def test_home_bind_allows_stale_coordinator_no_live():
    coord = {"nick": "flamingo-100", "seat": "100"}
    assert tsp.home_bind_refusal(
        coord,
        "flamingo-200",
        live_agent_nick=None,
        has_live_listen=False,
    ) is None


def test_home_bind_allows_reclaim_when_coord_matches_expected():
    coord = {"nick": "flamingo-22400", "seat": "22400"}
    assert tsp.home_bind_refusal(
        coord,
        "flamingo-22400",
        live_agent_nick="flamingo-old",
        has_live_listen=True,
    ) is None


def test_bind_home_cli_refuses(tmp_path: Path):
    home = tmp_path / "seat"
    home.mkdir()
    (home / "coordinator.pid").write_text(
        "nick=flamingo-100\nseat=100\nlisten=1\nagent=2\n", encoding="utf-8"
    )
    code = tsp.main(
        [
            "--bind-home",
            "--home",
            str(home),
            "--expected-nick",
            "flamingo-200",
            "--live-listen",
        ]
    )
    assert code == 3


def test_start_scripts_detach_listen_and_bind_guard():
    root = Path(__file__).resolve().parents[1]
    tsr = (root / "scripts" / "Start-IrcTsr.ps1").read_text(encoding="utf-8")
    talk = (root / "scripts" / "Start-TalkSeat.ps1").read_text(encoding="utf-8")
    assert "Start-Process" in tsr
    assert "listen.stdout.log" in tsr
    assert "RedirectStandardOutput" in tsr
    assert "talk_seat_pid.py" in tsr
    assert "--nick" in tsr and "--pid" in tsr
    assert "talk_seat_pid.py" in talk
    assert "--bind-home" in talk
    assert "--auto-nick" in talk
    assert "AGENTIC_IRC_SEAT_PID = 'self'" in talk
    assert "Stop-CursorHomeAgents" in talk
    assert (root / "scripts" / "start_talk_seat.py").is_file()
