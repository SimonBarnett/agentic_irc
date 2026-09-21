from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import talk_seat_pid as tsp


def test_parse_talk_seat_nick_flamingo():
    assert tsp.parse_talk_seat_nick("flamingo-17568") == ("flamingo", "17568")


def test_parse_talk_seat_long_machine_id():
    assert tsp.parse_talk_seat_nick("ce-priority-dev1-4412") == (
        "ce-priority-dev1",
        "4412",
    )


def test_parse_rejects_worker_and_bob():
    assert tsp.parse_talk_seat_nick("w-fl-4412") is None
    assert tsp.parse_talk_seat_nick("bob-ionos") is None


def test_validate_nick_seat_pid():
    assert tsp.validate_nick_seat_pid("flamingo-22400", 22400)
    assert not tsp.validate_nick_seat_pid("flamingo-17568", 22400)


def test_check_nick_seat_pid_message():
    err = tsp.check_nick_seat_pid("flamingo-17568", 22400)
    assert err and "17568" in err and "22400" in err
    assert "irc_listen" in err or "PowerShell" in err


def test_auto_talk_seat_nick():
    assert tsp.auto_talk_seat_nick("flamingo-1", 99999) == "flamingo-99999"


def test_parse_coordinator_pid_sample():
    text = """
nick=flamingo-22400
seat=22400
listen=17568
agent=19392
home=C:\\Users\\x\\.agentic-irc-cursor
"""
    doc = tsp.parse_coordinator_pid(text)
    assert doc["nick"] == "flamingo-22400"
    assert doc["seat"] == "22400"
    assert doc["listen"] == "17568"
    assert doc["agent"] == "19392"


def test_coordinator_mismatch_detected(tmp_path: Path):
    home = tmp_path / "seat"
    home.mkdir()
    (home / "coordinator.pid").write_text(
        "nick=flamingo-17568\nseat=22400\nlisten=17568\nagent=19392\n", encoding="utf-8"
    )
    assert tsp.check_coordinator_nick(home) is not None


def test_coordinator_match_ok(tmp_path: Path):
    home = tmp_path / "seat"
    home.mkdir()
    (home / "coordinator.pid").write_text(
        "nick=flamingo-22400\nseat=22400\nlisten=17568\nagent=19392\n", encoding="utf-8"
    )
    assert tsp.check_coordinator_nick(home) is None


def test_resolve_seat_pid_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_SEAT_PID", "4242")
    assert tsp.resolve_seat_pid(tmp_path) == 4242


def test_cli_guard_home(tmp_path: Path):
    home = tmp_path / "seat"
    home.mkdir()
    (home / "coordinator.pid").write_text(
        "nick=flamingo-100\nseat=100\n", encoding="utf-8"
    )
    assert tsp.main(["--home", str(home)]) == 0


def test_cli_guard_nick_pid():
    assert tsp.main(["--nick", "flamingo-50", "--pid", "50"]) == 0
    assert tsp.main(["--nick", "flamingo-50", "--pid", "51"]) == 2
