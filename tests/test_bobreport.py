from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bobreport


def setup_function() -> None:
    bobreport.reset_dedupe()


def test_shop_and_nick_helpers():
    assert bobreport.shop_channel("flamingo") == "#flamingo"
    assert bobreport.shop_channel("dev1") == "#ce-priority-dev1"
    assert bobreport.worker_key("flamingo", 4412) == "flamingo:4412"
    assert bobreport.worker_nick("flamingo", 4412) == "w-fl-4412"
    assert bobreport.worker_nick("marchhare", 2201) == "w-mh-2201"
    assert bobreport.worker_nick("ionos", 884) == "w-io-884"
    assert bobreport.worker_nick("ce-priority-dev1", 1024) == "w-d1-1024"
    assert bobreport.parse_worker_nick("w-fl-4412") == ("flamingo", "4412")
    assert bobreport.parse_worker_nick("w-fl-4412_") == ("flamingo", "4412")
    assert bobreport.parse_worker_nick("bob-flamingo") is None
    home = bobreport.worker_home("/tmp/irc", "flamingo", 4412)
    assert home.as_posix().endswith("workers/flamingo/4412")


def test_channels_for_nick():
    assert bobreport.channels_for_nick("bob-flamingo", "#bobiverse") == [
        "#bobiverse",
        "#flamingo",
    ]
    assert bobreport.channels_for_nick("w-fl-4412", "#bobiverse") == ["#flamingo"]
    assert bobreport.channels_for_nick("alice", "#ops") == ["#ops"]
    assert bobreport.normalize_channel("#dev1") == "#ce-priority-dev1"


def test_working_on_required_at_start(tmp_path):
    bad = bobreport.start_worker(tmp_path, "flamingo", 4412, "")
    assert not bad.ok
    ok = bobreport.start_worker(tmp_path, "flamingo", 4412, "agentic_irc shop-channel FR (BUILD)")
    assert ok.ok
    doc = bobreport.load_digest(tmp_path)
    w = doc["machines"]["flamingo"]["workers"]["4412"]
    assert w["working_on"].startswith("agentic_irc")
    assert w["key"] == "flamingo:4412"
    assert w["nick"] == "w-fl-4412"
    assert doc["machines"]["flamingo"]["status"] == "I am online"


def test_two_workers_one_shop(tmp_path):
    bobreport.start_worker(tmp_path, "flamingo", 4412, "job-a", kind="grok")
    bobreport.start_worker(tmp_path, "flamingo", 2201, "job-b", kind="cursor")
    doc = bobreport.load_digest(tmp_path)
    workers = doc["machines"]["flamingo"]["workers"]
    assert set(workers) == {"4412", "2201"}
    assert workers["4412"]["nick"] != workers["2201"]["nick"]
    assert doc["machines"]["flamingo"]["shop"] == "#flamingo"


def test_worker_quit_deletes_pid(tmp_path):
    bobreport.start_worker(tmp_path, "flamingo", 4412, "job-a")
    out = bobreport.apply_quit(tmp_path, "w-fl-4412")
    assert out.ok and out.deleted_pid == "4412"
    doc = bobreport.load_digest(tmp_path)
    assert "4412" not in doc["machines"]["flamingo"]["workers"]
    assert doc["machines"]["flamingo"]["online"] is True
    assert doc["machines"]["flamingo"]["status"] == "I am online"


def test_bob_quit_persists_offline_and_empties_workers(tmp_path):
    bobreport.start_worker(tmp_path, "ionos", 884, "job-a")
    out = bobreport.apply_quit(tmp_path, "bob-ionos")
    assert out.ok and out.shop_closed
    doc = bobreport.load_digest(tmp_path)
    ent = doc["machines"]["ionos"]
    assert ent["online"] is False
    assert ent["status"] == "I am offline"
    assert ent["workers"] == {}
    assert "ionos" in doc["machines"]
    obj = bobreport.build_digest_object(tmp_path, "bob-flamingo")
    assert obj["machines"]["ionos"]["status"] == "I am offline"
    assert "flamingo" in obj["machines"]


def test_report_scrubbed_not_ingested(tmp_path):
    out = bobreport.apply_report(
        tmp_path,
        "bob-ionos",
        "bob-flamingo",
        "!report TASK START SimonBarnett/agentic_build 8d9a852 composer-2.5 house-clean docs 12m",
    )
    assert not out.ok
    assert out.err == bobreport.REPORT_GONE
    doc = bobreport.load_digest(tmp_path)
    assert doc["machines"]["ionos"]["workers"] == {}
    assert "task" not in doc["machines"]["ionos"]


def test_refuse_secret_report_and_working_on(tmp_path):
    out = bobreport.apply_report(
        tmp_path,
        "bob-ionos",
        "bob-flamingo",
        "!report PCENT ionos cursor-models 50 password=leak",
    )
    assert not out.ok and out.err and "secret" in out.err.lower()
    bad = bobreport.start_worker(tmp_path, "flamingo", 1, "x XAI_API_KEY=abc")
    assert not bad.ok
    assert bobreport.split_irc_text("connect.password leaked") == []


def test_cc_traces_gated_on_pm_open():
    assert bobreport.route_cc("thinking", False) == frozenset()
    assert bobreport.route_cc("thinking", True) == frozenset({bobreport.CC_QUERY})
    assert bobreport.CC_SHOP not in bobreport.route_cc("tool", True)
    assert bobreport.route_cc("assistant", False) == frozenset({bobreport.CC_SHOP})
    assert bobreport.CC_QUERY in bobreport.route_cc("assistant", True)
    assert bobreport.route_cc("secret", True) == frozenset()
    assert bobreport.route_cc("working_on", True) == frozenset({bobreport.CC_SHOP})


def test_bobiverse_forms(tmp_path):
    assert bobreport.parse_bobiverse_query("!bobiverse") == ("full", None)
    assert bobreport.parse_bobiverse_query("!BOBIVERSE ?") == ("help", None)
    assert bobreport.parse_bobiverse_query("!bobiverse flamingo") == ("machine", "flamingo")
    assert bobreport.parse_bobiverse_query("!bobiverse dev1") == ("machine", "ce-priority-dev1")
    help_lines = bobreport.format_digest_whisper_lines(tmp_path, "bob-flamingo", form="help")
    assert help_lines == bobreport.HELP_TEXT.splitlines()
    assert "no !report" in "\n".join(help_lines)
    miss = bobreport.format_digest_whisper_lines(tmp_path, "bob-flamingo", form="machine", machine_id="nope")
    assert miss == [bobreport.NO_MACHINE]
    bobreport.start_worker(tmp_path, "flamingo", 4412, "agentic_irc shop-channel FR")
    one = bobreport.format_digest_whisper_lines(tmp_path, "bob-flamingo", form="machine", machine_id="flamingo")
    parsed = json.loads(one[0] if one[0].startswith("{") else one[-1].split(" ", 3)[-1])
    assert parsed["id"] == "flamingo"
    assert "4412" in parsed["workers"]
    full = bobreport.format_digest_whisper_lines(tmp_path, "bob-flamingo", form="full")
    pieces: list[str] = []
    for line in full:
        if line.startswith("{"):
            pieces.append(line)
        elif line.startswith("BOB DIGEST v1 "):
            pieces.append(line[len("BOB DIGEST v1 ") :].split(" ", 1)[1])
    obj = json.loads("".join(pieces))
    assert "ionos" in obj["machines"]
    assert obj["machines"]["ionos"]["status"] == "I am offline"


def test_callback_merge_delete_shop_down(tmp_path):
    out = bobreport.apply_callback(
        tmp_path,
        {
            "op": "merge",
            "machine": "flamingo",
            "pid": 4412,
            "kind": "grok",
            "working_on": "shop-channel FR",
            "pcent": {"cursor-models": 12},
        },
    )
    assert out.ok and out.changed and out.err == ""
    assert out.actions == ["'s pid 4412 on flamingo is working on shop-channel FR"]
    doc = bobreport.load_digest(tmp_path)
    assert doc["machines"]["flamingo"]["workers"]["4412"]["working_on"] == "shop-channel FR"
    assert doc["machines"]["flamingo"]["pcent"]["cursor-models"] == 12
    events_before_dup = len(bobreport.load_digest(tmp_path).get("events") or [])
    dup = bobreport.apply_callback(
        tmp_path,
        {
            "op": "merge",
            "machine": "flamingo",
            "pid": 4412,
            "kind": "grok",
            "working_on": "shop-channel FR",
            "pcent": {"cursor-models": 12},
        },
    )
    assert dup.ok and not dup.changed
    assert len(bobreport.load_digest(tmp_path).get("events") or []) == events_before_dup
    out2 = bobreport.apply_callback(tmp_path, {"op": "delete-worker", "machine": "flamingo", "pid": 4412})
    assert out2.ok
    doc = bobreport.load_digest(tmp_path)
    assert doc["machines"]["flamingo"]["workers"] == {}
    out3 = bobreport.apply_callback(tmp_path, {"op": "shop-down", "machine": "flamingo"})
    assert out3.ok
    doc = bobreport.load_digest(tmp_path)
    assert doc["machines"]["flamingo"]["status"] == "I am offline"
    bad = bobreport.apply_callback(tmp_path, {"op": "merge", "machine": "flamingo", "secret": "nope"})
    assert not bad.ok


def test_disconnect_dedupe(tmp_path):
    bobreport.start_worker(tmp_path, "flamingo", 9, "x")
    bobreport.delete_worker(tmp_path, "flamingo", 9, now=100.0)
    bobreport.start_worker(tmp_path, "flamingo", 9, "y")
    bobreport.delete_worker(tmp_path, "flamingo", 9, now=110.0)
    doc = bobreport.load_digest(tmp_path)
    assert "9" in doc["machines"]["flamingo"]["workers"]
    bobreport.delete_worker(tmp_path, "flamingo", 9, now=140.0)
    doc = bobreport.load_digest(tmp_path)
    assert "9" not in doc["machines"]["flamingo"]["workers"]
