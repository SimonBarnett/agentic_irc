from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bobstat
import bobtalk
import irc_agent
import moot
import wire

MID = bobtalk.FLEET_MOOT_ID


def _args(home: Path, nick: str = "bob-flamingo", channel: str = "#bobiverse") -> argparse.Namespace:
    return argparse.Namespace(
        nick=nick,
        channel=channel,
        home=str(home),
        outbox="",
        hello="",
        announce_key=False,
        host="127.0.0.1",
        port=6697,
        realname="test",
        once=True,
        password="",
    )


def _open_moot(home: Path, chair: str = "bob-flamingo") -> dict:
    return moot.apply_moot(
        {},
        chair,
        wire.parse_moot_line(f"MOOT v1 OPEN {MID} {chair} free :bobiverse"),
        home,
    )


@pytest.fixture
def recorder(monkeypatch):
    sent: list[str] = []

    def _send(self, line: str) -> None:
        sent.append(line)

    monkeypatch.setattr(irc_agent.Client, "send", _send)
    monkeypatch.setattr(irc_agent.time, "sleep", lambda *_a, **_k: None)
    return sent


def test_whisper_not_channel(tmp_path, monkeypatch, recorder):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    c = irc_agent.Client(_args(tmp_path))
    c.whisper("simon", "hello there")
    assert recorder == ["PRIVMSG simon :hello there"]
    assert not any("#bobiverse" in x for x in recorder)


def test_bobiverse_human_in_channel(tmp_path, monkeypatch, recorder):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    _open_moot(tmp_path)
    bobstat.write_peer(
        tmp_path,
        {
            "ok": True,
            "id": "ionos",
            "running": 0,
            "queued": 0,
            "jobs": [],
        },
    )
    c = irc_agent.Client(_args(tmp_path, "bob-flamingo"))
    c.handle_privmsg("simon!u@h", "#bobiverse", "!bobiverse")
    assert any("#bobiverse" in x and "ionos is idle" in x for x in recorder)
    assert not any(x.startswith("PRIVMSG simon :") for x in recorder)

    recorder.clear()
    c2 = irc_agent.Client(_args(tmp_path, "bob-ionos"))
    c2.handle_privmsg("simon!u@h", "#bobiverse", "!bobiverse")
    assert recorder == []


def test_bobiverse_tray_whisper_to_agent(tmp_path, monkeypatch, recorder):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    _open_moot(tmp_path)
    bobstat.write_peer(
        tmp_path,
        {
            "ok": True,
            "id": "ionos",
            "running": 1,
            "queued": 0,
            "repo": "?",
            "jobs": [{"repo": "SimonBarnett/agentic_irc", "state": "running"}],
        },
    )
    c = irc_agent.Client(_args(tmp_path, "bob-flamingo"))
    c.handle_privmsg("bob-marchhare!u@h", "#bobiverse", "!bobiverse")
    assert recorder
    assert all(x.startswith("PRIVMSG bob-marchhare :") for x in recorder)
    assert not any("#bobiverse" in x for x in recorder)
    assert any("BOB TRAY v1" in x and "repo=SimonBarnett/agentic_irc" in x for x in recorder)


def test_bobiverse_cooldown_human(tmp_path, monkeypatch, recorder):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    _open_moot(tmp_path)
    bobstat.write_peer(tmp_path, {"ok": True, "id": "flamingo", "running": 0, "queued": 0, "jobs": []})
    c = irc_agent.Client(_args(tmp_path, "bob-flamingo"))
    c.handle_privmsg("simon!u@h", "#bobiverse", "!bobiverse")
    n1 = len(recorder)
    assert n1 >= 1
    c.handle_privmsg("simon!u@h", "#bobiverse", "!bobiverse")
    assert len(recorder) == n1


def test_bobiverse_cooldown_agent_separate(tmp_path, monkeypatch, recorder):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    _open_moot(tmp_path)
    bobstat.write_peer(tmp_path, {"ok": True, "id": "flamingo", "running": 0, "queued": 0, "jobs": []})
    c = irc_agent.Client(_args(tmp_path, "bob-flamingo"))
    c.handle_privmsg("bob-marchhare!u@h", "#bobiverse", "!bobiverse")
    n1 = len(recorder)
    c.handle_privmsg("bob-marchhare!u@h", "#bobiverse", "!bobiverse")
    assert len(recorder) == n1
    c.handle_privmsg("simon!u@h", "#bobiverse", "!bobiverse")
    assert len(recorder) > n1


def test_join_brief_sequence(tmp_path, monkeypatch, recorder):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    _open_moot(tmp_path)
    bobstat.write_peer(tmp_path, {"ok": True, "id": "flamingo", "running": 0, "queued": 0, "jobs": []})
    bobstat.write_peer(
        tmp_path,
        {
            "ok": True,
            "id": "ionos",
            "running": 1,
            "queued": 0,
            "model": "Cursor Models",
            "kind": "worker",
            "repo": "SimonBarnett/agentic_irc",
            "jobs": [{"repo": "SimonBarnett/agentic_irc", "state": "running"}],
        },
    )
    c = irc_agent.Client(_args(tmp_path, "bob-flamingo"))
    c.handle_privmsg("bob-ionos!u@h", "#bobiverse", f"MOOT v1 JOIN {MID}")
    assert len(recorder) >= 2
    assert all(x.startswith("PRIVMSG bob-ionos :") for x in recorder)
    assert not any("#bobiverse" in x for x in recorder)


def test_moot_join_non_fleet_not_briefed(tmp_path, monkeypatch, recorder):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    _open_moot(tmp_path)
    bobstat.write_peer(tmp_path, {"ok": True, "id": "flamingo", "running": 0, "queued": 0, "jobs": []})
    c = irc_agent.Client(_args(tmp_path, "bob-flamingo"))
    c.handle_privmsg("simon!u@h", "#bobiverse", f"MOOT v1 JOIN {MID}")
    assert recorder == []


def test_bobiverse_via_pm_to_bob(tmp_path, monkeypatch, recorder):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    _open_moot(tmp_path)
    bobstat.write_peer(tmp_path, {"ok": True, "id": "flamingo", "running": 0, "queued": 0, "jobs": []})
    c = irc_agent.Client(_args(tmp_path, "bob-flamingo"))
    c.handle_privmsg("simon!u@h", "bob-flamingo", "!bobiverse")
    assert recorder and recorder[0].startswith("PRIVMSG simon :")


def test_point_change_talk_on_channel(tmp_path, monkeypatch, recorder):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    _open_moot(tmp_path)
    bobstat.write_peer(
        tmp_path,
        {
            "ok": True,
            "id": "ionos",
            "running": 0,
            "queued": 0,
            "jobs": [],
        },
    )
    c = irc_agent.Client(_args(tmp_path, "bob-flamingo"))
    point = (
        "MOOT v1 POINT "
        + MID
        + " :BOB v1 id=ionos weekly=4 running=1 queued=0 "
        "lastSeen=2026-09-21T00:00:00Z jobs=SimonBarnett/agentic_irc:running"
    )
    c.handle_privmsg("bob-ionos!u@h", "#bobiverse", point)
    assert any("#bobiverse" in x for x in recorder)
