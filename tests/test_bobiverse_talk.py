from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bobreport
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


def test_bobiverse_human_gets_json_whisper(tmp_path, monkeypatch, recorder):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    _open_moot(tmp_path)
    bobreport.apply_report(
        tmp_path,
        "bob-ionos",
        "bob-flamingo",
        "!report PCENT ionos cursor-models 12",
    )
    c = irc_agent.Client(_args(tmp_path, "bob-flamingo"))
    c.handle_privmsg("simon!u@h", "#bobiverse", "!bobiverse")
    assert any(x.startswith("PRIVMSG simon :") for x in recorder)
    assert not any("#bobiverse" in x for x in recorder)
    body = recorder[0].split(" :", 1)[1]
    doc = json.loads(body)
    assert doc["v"] == 1
    assert "machines" in doc


def test_bobiverse_non_briefer_silent(tmp_path, monkeypatch, recorder):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    _open_moot(tmp_path)
    bobstat.write_peer(tmp_path, {"ok": True, "id": "flamingo", "running": 0, "queued": 0, "jobs": []})
    c2 = irc_agent.Client(_args(tmp_path, "bob-ionos"))
    c2.handle_privmsg("simon!u@h", "#bobiverse", "!bobiverse")
    assert recorder == []


def test_bobiverse_tray_whisper_json(tmp_path, monkeypatch, recorder):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    _open_moot(tmp_path)
    bobreport.apply_report(
        tmp_path,
        "bob-ionos",
        "bob-flamingo",
        "!report TASK START SimonBarnett/agentic_irc abcdef1 grok work 1m",
    )
    c = irc_agent.Client(_args(tmp_path, "bob-flamingo"))
    c.handle_privmsg("bob-marchhare!u@h", "#bobiverse", "!bobiverse")
    assert recorder
    assert all(x.startswith("PRIVMSG bob-marchhare :") for x in recorder)
    assert not any("#bobiverse" in x for x in recorder)
    payload = recorder[0].split(" :", 1)[1]
    assert payload.startswith("{")
    assert "BOB TRAY v1" not in payload


def test_bobiverse_cooldown_human(tmp_path, monkeypatch, recorder):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    _open_moot(tmp_path)
    bobreport.save_digest(tmp_path, bobreport.empty_digest())
    c = irc_agent.Client(_args(tmp_path, "bob-flamingo"))
    c.handle_privmsg("simon!u@h", "#bobiverse", "!bobiverse")
    n1 = len(recorder)
    assert n1 >= 1
    c.handle_privmsg("simon!u@h", "#bobiverse", "!bobiverse")
    assert len(recorder) == n1


def test_bobiverse_cooldown_agent_separate(tmp_path, monkeypatch, recorder):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    _open_moot(tmp_path)
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
    c = irc_agent.Client(_args(tmp_path, "bob-flamingo"))
    c.handle_privmsg("simon!u@h", "bob-flamingo", "!bobiverse")
    assert recorder and recorder[0].startswith("PRIVMSG simon :")


def test_point_no_channel_talk(tmp_path, monkeypatch, recorder):
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
    assert not any("#bobiverse" in x for x in recorder)


def test_report_ingest_no_raw_echo(tmp_path, monkeypatch, recorder):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    _open_moot(tmp_path)
    c = irc_agent.Client(_args(tmp_path, "bob-flamingo"))
    raw = "!report TASK START SimonBarnett/agentic_build 8d9a852 composer-2.5 house-clean docs 12m"
    c.handle_privmsg("bob-ionos!u@h", "#bobiverse", raw)
    assert not any(raw in x for x in recorder)
    assert any("#bobiverse" in x and "started" in x for x in recorder)


def test_report_non_briefer_ignored(tmp_path, monkeypatch, recorder):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    _open_moot(tmp_path, chair="bob-flamingo")
    c = irc_agent.Client(_args(tmp_path, "bob-ionos"))
    c.handle_privmsg("bob-marchhare!u@h", "#bobiverse", "!report PCENT ionos cursor-models 50")
    assert recorder == []


def _report_help_privmsg_payloads(recorder: list[str], asker: str) -> list[str]:
    prefix = f"PRIVMSG {asker} :"
    return [line.split(" :", 1)[1] for line in recorder if line.startswith(prefix)]


def test_report_help_whispers_per_line_channel_and_pm(tmp_path, monkeypatch, recorder):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    _open_moot(tmp_path, chair="bob-flamingo")
    expected = bobreport.HELP_TEXT.splitlines()
    c = irc_agent.Client(_args(tmp_path, "bob-flamingo"))

    c.handle_privmsg("simon!u@h", "#bobiverse", "!report ?")
    assert len(recorder) == len(expected)
    assert all(x.startswith("PRIVMSG simon :") for x in recorder)
    assert not any("#bobiverse" in x for x in recorder)
    assert _report_help_privmsg_payloads(recorder, "simon") == expected
    for line in recorder:
        payload = line.split(" :", 1)[1]
        assert "\n" not in payload and "\r" not in payload

    recorder.clear()
    c.handle_privmsg("simon!u@h", "bob-flamingo", "!report help")
    assert len(recorder) == len(expected)
    assert all(x.startswith("PRIVMSG simon :") for x in recorder)
    assert not any("#bobiverse" in x for x in recorder)
    assert _report_help_privmsg_payloads(recorder, "simon") == expected

    recorder.clear()
    c2 = irc_agent.Client(_args(tmp_path, "bob-ionos"))
    c2.handle_privmsg("simon!u@h", "#bobiverse", "!report ?")
    assert recorder == []
