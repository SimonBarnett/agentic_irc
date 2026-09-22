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


def _args(
    home: Path, nick: str = "bob-flamingo", channel: str = "#bobiverse", chair: bool = False
) -> argparse.Namespace:
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
        chair=chair,
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


def _json_whisper_payloads(recorder: list[str], asker: str) -> list[str]:
    prefix = f"PRIVMSG {asker} :"
    out: list[str] = []
    for line in recorder:
        if not line.startswith(prefix):
            continue
        body = line.split(" :", 1)[1]
        if body.startswith("{") or body.startswith("BOB DIGEST v1"):
            out.append(body)
    return out


def _reassemble_digest(lines: list[str]) -> dict:
    pieces: list[str] = []
    for body in lines:
        if body.startswith("{"):
            pieces.append(body)
        elif body.startswith("BOB DIGEST v1 "):
            rest = body[len("BOB DIGEST v1 ") :]
            pieces.append(rest.split(" ", 1)[1])
    return json.loads("".join(pieces))


def test_bobiverse_human_gets_json_whisper(tmp_path, monkeypatch, recorder):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    _open_moot(tmp_path)
    bobreport.apply_callback(
        tmp_path,
        {"op": "merge", "machine": "ionos", "pid": 12, "working_on": "meter", "kind": "cursor"},
        "bob-flamingo",
    )
    c = irc_agent.Client(_args(tmp_path, "bob-flamingo"))
    assert "#flamingo" in c.channels
    c.handle_privmsg("simon!u@h", "#bobiverse", "!bobiverse")
    assert any(x.startswith("PRIVMSG simon :") for x in recorder)
    assert not any(x.startswith("PRIVMSG #bobiverse :{") for x in recorder)
    payloads = _json_whisper_payloads(recorder, "simon")
    assert payloads
    doc = _reassemble_digest(payloads)
    assert doc["v"] == 1
    assert "machines" in doc
    assert "ionos" in doc["machines"]


def test_bobiverse_non_briefer_silent(tmp_path, monkeypatch, recorder):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    _open_moot(tmp_path)
    bobstat.write_peer(tmp_path, {"ok": True, "id": "flamingo", "running": 0, "queued": 0, "jobs": []})
    c2 = irc_agent.Client(_args(tmp_path, "bob-ionos"))
    c2.handle_privmsg("simon!u@h", "#bobiverse", "!bobiverse")
    assert recorder == []


def test_chair_answers_bobiverse_builder_silent(tmp_path, monkeypatch, recorder):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    _open_moot(tmp_path, chair="bob-chair")
    bobreport.persist_chair_nick(tmp_path, "bob-chair")
    bobreport.apply_callback(
        tmp_path,
        {"op": "merge", "machine": "ionos", "pid": 12, "working_on": "meter", "kind": "cursor"},
        "bob-chair",
    )
    builder = irc_agent.Client(_args(tmp_path, "bob-ionos"))
    builder.handle_privmsg("simon!u@h", "#bobiverse", "!bobiverse")
    assert recorder == []
    chair = irc_agent.Client(_args(tmp_path, "bob-chair", chair=True))
    assert bobreport.load_digest(tmp_path).get("chairNick") == "bob-chair"
    assert chair.channels == [
        "#bobiverse",
        "#flamingo",
        "#marchhare",
        "#ionos",
        "#ce-priority-dev1",
    ]
    chair.handle_privmsg("simon!u@h", "#bobiverse", "!bobiverse")
    assert any(x.startswith("PRIVMSG simon :") for x in recorder)
    assert not any("BOB DIGEST" in x and "#bobiverse" in x for x in recorder)


def test_chair_mode_no_fleet_action_on_callback(tmp_path, monkeypatch, recorder):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    bobreport.persist_chair_nick(tmp_path, "bob-chair")
    _open_moot(tmp_path, chair="bob-chair")
    chair = irc_agent.Client(_args(tmp_path, "bob-chair", chair=True))
    chair.apply_digest_callback(
        {"op": "merge", "machine": "flamingo", "pid": 4412, "working_on": "callback job", "kind": "cursor"}
    )
    assert bobreport.load_digest(tmp_path)["machines"]["flamingo"]["workers"]["4412"]["working_on"] == "callback job"
    assert not any("#bobiverse" in x and "ACTION" in x for x in recorder)


def test_chair_mention_silent_on_channel(tmp_path, monkeypatch, recorder):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    bobreport.persist_chair_nick(tmp_path, "bob-chair")
    chair = irc_agent.Client(_args(tmp_path, "bob-chair", chair=True))
    chair.handle_privmsg("simon!u@h", "#bobiverse", "bob-chair: are you there")
    assert recorder == []


def test_chair_drains_outbox_without_bobiverse_spam(tmp_path, monkeypatch, recorder):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    bobreport.persist_chair_nick(tmp_path, "bob-chair")
    chair = irc_agent.Client(_args(tmp_path, "bob-chair", chair=True))
    chair.sock = object()
    chair.joined.set()
    outbox = chair.outbox
    outbox.write_text(
        "\n".join(
            [
                "JOIN #bobiverse",
                "BOB DIGEST v1 1/1 {}",
                "flamingo: I am offline",
                "PRIVMSG #bobiverse :BOB DIGEST v1 1/2 {}",
                bobtalk.TRAY_PREFIX + "id=ionos weekly=3 running=0 queued=0 repo=- kind=- model=- lastSeen=- jobs=-",
                "PRIVMSG #ionos :shop ok",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    sent = chair.drain_outbox_once()
    assert "JOIN #bobiverse" in sent
    assert any(x.startswith("PRIVMSG #ionos :") for x in recorder)
    assert not any("#bobiverse" in x and "BOB DIGEST" in x for x in recorder)
    assert not any("#bobiverse" in x and "I am offline" in x for x in recorder)
    assert not any("#bobiverse" in x and bobtalk.TRAY_PREFIX.strip() in x for x in recorder)


def test_bobiverse_tray_whisper_json(tmp_path, monkeypatch, recorder):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    _open_moot(tmp_path)
    bobreport.start_worker(tmp_path, "ionos", 99, "work 1m", kind="grok")
    c = irc_agent.Client(_args(tmp_path, "bob-flamingo"))
    c.handle_privmsg("bob-marchhare!u@h", "#bobiverse", "!bobiverse")
    assert recorder
    assert all(x.startswith("PRIVMSG bob-marchhare :") for x in recorder)
    assert not any(x.startswith("PRIVMSG #bobiverse :") and "{" in x for x in recorder)
    payloads = _json_whisper_payloads(recorder, "bob-marchhare")
    assert payloads
    doc = _reassemble_digest(payloads)
    assert doc["v"] == 1
    assert "BOB TRAY v1" not in "".join(payloads)


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
    assert not any("#bobiverse" in x and "started" in x for x in recorder)
    assert any(x == f"PRIVMSG bob-ionos :{bobreport.REPORT_GONE}" for x in recorder)
    doc = bobreport.load_digest(tmp_path)
    assert "task" not in doc["machines"]["ionos"]


def test_report_non_briefer_ignored(tmp_path, monkeypatch, recorder):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    _open_moot(tmp_path, chair="bob-flamingo")
    c = irc_agent.Client(_args(tmp_path, "bob-ionos"))
    c.handle_privmsg("bob-marchhare!u@h", "#bobiverse", "!report PCENT ionos cursor-models 50")
    assert recorder == []


def test_report_gone_whisper_once(tmp_path, monkeypatch, recorder):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    _open_moot(tmp_path, chair="bob-flamingo")
    c = irc_agent.Client(_args(tmp_path, "bob-flamingo"))

    c.handle_privmsg("simon!u@h", "#bobiverse", "!report ?")
    assert recorder == [f"PRIVMSG simon :{bobreport.REPORT_GONE}"]
    recorder.clear()
    c.handle_privmsg("simon!u@h", "bob-flamingo", "!report help")
    assert recorder == []

    recorder.clear()
    c2 = irc_agent.Client(_args(tmp_path, "bob-ionos"))
    c2.handle_privmsg("simon!u@h", "#bobiverse", "!report ?")
    assert recorder == []


def test_bobiverse_help_and_machine(tmp_path, monkeypatch, recorder):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    _open_moot(tmp_path)
    c = irc_agent.Client(_args(tmp_path, "bob-flamingo"))
    c.handle_privmsg("simon!u@h", "#bobiverse", "!bobiverse ?")
    got = [line.split(" :", 1)[1] for line in recorder if line.startswith("PRIVMSG simon :")]
    assert got == bobreport.HELP_TEXT.splitlines()
    recorder.clear()
    c._bobiverse_last_query.clear()
    c.handle_privmsg("simon!u@h", "#bobiverse", "!bobiverse nope")
    assert any(bobreport.NO_MACHINE in x for x in recorder)


def test_working_on_shop_line_and_bob_action(tmp_path, monkeypatch, recorder):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    _open_moot(tmp_path)
    job = "agentic_irc shop-channel FR (BUILD)"
    shop_line = bobreport.working_on_shop_line("w-fl-4412", job)
    w = irc_agent.Client(_args(tmp_path, "w-fl-4412", channel="#flamingo"))
    w.cc_send("working_on", job)
    assert bobreport.load_digest(tmp_path)["machines"]["flamingo"]["workers"]["4412"]["working_on"] == job
    assert recorder == [f"PRIVMSG #flamingo :{shop_line}"]
    recorder.clear()
    w.cc_send("working_on", job)
    assert recorder == []
    w.cc_send("assistant", "visible stdout")
    assert recorder == ["PRIVMSG #flamingo :visible stdout"]
    assert not any("#bobiverse" in x for x in recorder)
    recorder.clear()
    bob = irc_agent.Client(_args(tmp_path, "bob-flamingo"))
    bob.handle_privmsg("w-fl-4412!u@h", "#flamingo", shop_line)
    assert not any(x.startswith("PRIVMSG #flamingo :") for x in recorder)
    assert any(
        x.startswith("PRIVMSG #bobiverse :")
        and "ACTION" in x
        and "pid 4412 on flamingo is working on" in x
        for x in recorder
    )
    recorder.clear()
    bob.handle_privmsg("w-fl-4412!u@h", "#flamingo", shop_line)
    assert not any("ACTION" in x for x in recorder)


def test_working_on_callback_emits_bob_action(tmp_path, monkeypatch, recorder):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    _open_moot(tmp_path)
    c = irc_agent.Client(_args(tmp_path, "bob-flamingo"))
    c.apply_digest_callback(
        {"op": "merge", "machine": "flamingo", "pid": 4412, "working_on": "callback job", "kind": "cursor"}
    )
    assert bobreport.load_digest(tmp_path)["machines"]["flamingo"]["workers"]["4412"]["working_on"] == "callback job"
    assert any(
        x.startswith("PRIVMSG #bobiverse :") and "ACTION" in x and "callback job" in x for x in recorder
    )
    recorder.clear()
    c.apply_digest_callback(
        {"op": "merge", "machine": "flamingo", "pid": 4412, "working_on": "callback job", "kind": "cursor"}
    )
    assert not any("ACTION" in x for x in recorder)


def test_quit_worker_and_bob_action(tmp_path, monkeypatch, recorder):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    _open_moot(tmp_path)
    bobreport.start_worker(tmp_path, "flamingo", 4412, "shop-channel FR")
    bobreport.start_worker(tmp_path, "ionos", 884, "other")
    c = irc_agent.Client(_args(tmp_path, "bob-flamingo"))
    c.handle_quit("w-fl-4412")
    assert "4412" not in bobreport.load_digest(tmp_path)["machines"]["flamingo"]["workers"]
    assert any(
        x.startswith("PRIVMSG #bobiverse :") and "ACTION" in x and "w-fl-4412" in x for x in recorder
    )
    assert not any(x.startswith("PRIVMSG #flamingo :") for x in recorder)
    recorder.clear()
    c.handle_quit("bob-ionos")
    doc = bobreport.load_digest(tmp_path)
    assert doc["machines"]["ionos"]["status"] == "I am offline"
    assert doc["machines"]["ionos"]["workers"] == {}
    assert any("lost bob-ionos" in x and x.startswith("PRIVMSG #bobiverse :") for x in recorder)


def test_worker_cc_pm_open(tmp_path, monkeypatch, recorder):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    c = irc_agent.Client(_args(tmp_path, "w-fl-4412", channel="#flamingo"))
    assert c.channels == ["#flamingo"]
    c.cc_send("thinking", "trace line")
    assert recorder == []
    c.handle_privmsg("simon!u@h", "w-fl-4412", "hello")
    c.cc_send("thinking", "trace line")
    assert any(x == "PRIVMSG simon :trace line" for x in recorder)
    assert not any("#flamingo" in x and "trace line" in x for x in recorder)
    recorder.clear()
    c.cc_send("assistant", "visible stdout")
    assert any(x == "PRIVMSG #flamingo :visible stdout" for x in recorder)
    recorder.clear()
    c.cc_send("thinking", "password=secret")
    assert recorder == []


def test_worker_433_suffix():
    assert bobreport.parse_worker_nick("w-io-884_") == ("ionos", "884")


def test_joined_waits_for_every_channel(tmp_path, monkeypatch, recorder):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    c = irc_agent.Client(_args(tmp_path, "bob-flamingo"))
    assert {x.lower() for x in c.channels} == {"#bobiverse", "#flamingo"}
    assert not c.joined.is_set()
    c.handle_join("bob-flamingo", "#bobiverse")
    assert not c.joined.is_set()
    c.handle_join("bob-flamingo", "#flamingo")
    assert c.joined.is_set()


def test_shop_closed_whispers_open_query(tmp_path, monkeypatch, recorder):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    c = irc_agent.Client(_args(tmp_path, "w-fl-4412", channel="#flamingo"))
    c.handle_privmsg("simon!u@h", "w-fl-4412", "hello")
    recorder.clear()
    c.handle_quit("bob-flamingo")
    assert any(x == "PRIVMSG simon :shop closed" for x in recorder)
    assert c.stop.is_set()


def test_briefer_prefers_online_when_chair_not_bob():
    state = {"chair": "simon", "roster": ["simon", "bob-ionos", "bob-flamingo"]}
    assert bobtalk.briefer_nick(state) == "bob-ionos"
    assert bobtalk.briefer_nick(state, {"bob-flamingo"}) == "bob-flamingo"
