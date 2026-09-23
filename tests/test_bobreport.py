from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bobreport
import bobstat


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
    assert bobreport.channels_for_nick("bob-ionos", "#bobiverse") == [
        "#bobiverse",
        "#ionos",
    ]
    assert bobreport.channels_for_nick("w-io-4412", "#bobiverse") == ["#ionos"]
    assert bobreport.channels_for_nick("alice", "#ops") == ["#ops"]
    assert bobreport.normalize_channel("#dev1") == "#ce-priority-dev1"
    # Talk seats share #{machine} with bob-* and rejoin #bobiverse (issue #108).
    assert bobreport.parse_talk_seat_nick("ce-priority-dev1-16948") == "ce-priority-dev1"
    assert bobreport.parse_talk_seat_nick("flamingo-17568") == "flamingo"
    assert bobreport.parse_talk_seat_nick("bob-flamingo") is None
    assert bobreport.channels_for_nick(
        "ce-priority-dev1-16948", "#bobiverse,#ce-priority-dev1,#agentic_irc"
    ) == ["#bobiverse", "#ce-priority-dev1", "#agentic_irc"]
    assert bobreport.channels_for_nick("marchhare-20280", "#bobiverse,#marchhare") == [
        "#bobiverse",
        "#marchhare",
    ]
    assert bobreport.chair_channels() == [
        "#bobiverse",
        "#flamingo",
        "#marchhare",
        "#ionos",
        "#ce-priority-dev1",
    ]


def test_worker_irc_agent_args_ionos():
    args = bobreport.worker_irc_agent_args("/tmp/fleet", "ionos", 4412)
    assert args["nick"] == "w-io-4412"
    assert args["channel"] == "#ionos"
    assert args["home"].replace("\\", "/").endswith("workers/ionos/4412")


def test_expand_join_channels():
    assert bobreport.expand_join_channels("#bobiverse,#ionos") == [
        "#bobiverse",
        "#ionos",
    ]
    assert bobreport.expand_join_channels(":#bobiverse,#ionos") == [
        "#bobiverse",
        "#ionos",
    ]


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
    assert bobreport.route_cc("working_on", True) == frozenset()


def test_bobiverse_forms(tmp_path):
    assert bobreport.parse_bobiverse_query("!bobiverse") == ("full", None)
    assert bobreport.parse_bobiverse_query("!BOBIVERSE ?") == ("help", None)
    assert bobreport.parse_bobiverse_query("!bobiverse flamingo") == ("machine", "flamingo")
    assert bobreport.parse_bobiverse_query("!bobiverse dev1") == ("machine", "ce-priority-dev1")
    assert bobreport.BOBIVERSE_GONE.startswith("ERR !bobiverse gone")
    assert "bob.ntsa.uk" in bobreport.digest_url()
    help_lines = bobreport.format_digest_whisper_lines(tmp_path, "bob-flamingo", form="help")
    assert help_lines == bobreport.HELP_TEXT.splitlines()
    assert "no !report" in "\n".join(help_lines)
    assert "bob.ntsa.uk" in "\n".join(help_lines)
    miss = bobreport.format_digest_whisper_lines(tmp_path, "bob-flamingo", form="machine", machine_id="nope")
    assert miss == [bobreport.NO_MACHINE]
    bobreport.start_worker(tmp_path, "flamingo", 4412, "agentic_irc shop-channel FR")
    one = bobreport.format_digest_whisper_lines(tmp_path, "bob-flamingo", form="machine", machine_id="flamingo")
    parsed = _digest_json_from_whisper(one)
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


def test_cursor_pools_lesser_across_machines(tmp_path):
    bobreport.apply_callback(
        tmp_path,
        {"op": "merge", "machine": "flamingo", "pcent": {"cursor-models": 80}},
    )
    bobreport.apply_callback(
        tmp_path,
        {"op": "merge", "machine": "ionos", "pcent": {"cursor-models": 12}},
    )
    obj = bobreport.build_digest_object(tmp_path, "Jeeves")
    models = next(p for p in obj["cursor_pools"] if p.get("id") == "cursor-models")
    assert models["remaining"] == 12
    bobreport.apply_callback(
        tmp_path,
        {"op": "merge", "machine": "flamingo", "pcent": {"cursor-models": 99}, "weekly": 90},
    )
    bobreport.apply_callback(
        tmp_path,
        {"op": "merge", "machine": "flamingo", "weekly": 40},
    )
    ent = bobreport.load_digest(tmp_path)["machines"]["flamingo"]
    assert ent["pcent"]["cursor-models"] == 80
    assert ent["weekly"] == 40
    obj2 = bobreport.build_digest_object(tmp_path, "Jeeves")
    models2 = next(p for p in obj2["cursor_pools"] if p.get("id") == "cursor-models")
    assert models2["remaining"] == 12


def test_watch_metrics_script_present():
    root = Path(__file__).resolve().parents[1]
    script = root / "tools" / "Watch-BobDigestMetrics.ps1"
    assert script.is_file()
    text = script.read_text(encoding="utf-8")
    assert "IntervalSeconds = 120" in text
    assert "Get-BobWeeklyRemaining" in text
    assert "bob/v1/report" in text


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


def test_merge_peer_fields_fuel_and_duplicate(tmp_path):
    payload = {
        "op": "merge",
        "machine": "ionos",
        "fuel": "Cursor Models",
        "weekly": 3,
        "model": "Cursor Models",
        "repo": "agentic_irc",
        "sha": "abc1234",
        "cursor_label": "Composer",
        "jobs": [{"repo": "agentic_irc", "state": "running"}],
    }
    out = bobreport.apply_callback(tmp_path, payload)
    assert out.ok and out.changed
    ent = bobreport.load_digest(tmp_path)["machines"]["ionos"]
    assert ent["fuel"] == "Cursor Models"
    assert ent["weekly"] == 3
    assert ent["model"] == "Cursor Models"
    assert ent["repo"] == "agentic_irc"
    assert ent["sha"] == "abc1234"
    assert ent["cursor_label"] == "Composer"
    assert ent["jobs"] == [{"repo": "agentic_irc", "state": "running"}]
    events_n = len(bobreport.load_digest(tmp_path).get("events") or [])
    dup = bobreport.apply_callback(tmp_path, dict(payload))
    assert dup.ok and not dup.changed
    assert len(bobreport.load_digest(tmp_path).get("events") or []) == events_n
    changed = bobreport.apply_callback(tmp_path, {**payload, "fuel": "grok.exe"})
    assert changed.ok and changed.changed
    assert bobreport.load_digest(tmp_path)["machines"]["ionos"]["fuel"] == "grok.exe"


TRAY_MACHINE_REQUIRED = (
    "id",
    "nick",
    "shop",
    "online",
    "status",
    "working_on",
    "workers",
    "weekly",
    "period_end",
    "lastSeen",
    "running",
    "queued",
    "jobs",
)


def _digest_json_from_whisper(lines: list[str]) -> dict:
    pieces: list[str] = []
    for line in lines:
        if line.startswith("{"):
            pieces.append(line)
        elif line.startswith("BOB DIGEST v1 "):
            pieces.append(line[len("BOB DIGEST v1 ") :].split(" ", 1)[1])
    return json.loads("".join(pieces))


def test_build_digest_tray_complete_shape(tmp_path):
    bobreport.apply_callback(
        tmp_path,
        {
            "op": "merge",
            "machine": "ionos",
            "weekly": 42,
            "lastSeen": "2026-09-21T00:00:00Z",
            "running": 1,
            "queued": 0,
            "period_end": "2026-09-28T00:00:00Z",
            "jobs": [
                {
                    "repo": "SimonBarnett/agentic_irc",
                    "sha": "abc1234",
                    "model": "composer-2.5",
                    "description": "systray digest",
                    "state": "running",
                    "run_time": "5m",
                }
            ],
            "pcent": {"cursor-models": 55},
            "cursor_label": "Composer",
        },
    )
    doc = bobreport.load_digest(tmp_path)
    doc["cursor_pools"] = [
        {
            "group": "cursor-models",
            "label": "Cursor Models",
            "remaining": 55,
            "period_end": "2026-09-28T00:00:00Z",
        }
    ]
    doc["chairNick"] = "Jeeves"
    bobreport.save_digest(tmp_path, doc)
    bobstat.write_peer(
        tmp_path,
        {
            "ok": True,
            "id": "flamingo",
            "weekly": 8,
            "running": 0,
            "queued": 1,
            "lastSeen": "2026-09-21T01:00:00Z",
            "jobs": [],
        },
    )
    obj = bobreport.build_digest_object(tmp_path, "bob-flamingo")
    assert obj["chairNick"] == "Jeeves"
    assert len(obj["cursor_pools"]) >= 1
    for mid in bobreport.FLEET_MACHINE_IDS:
        ent = obj["machines"][mid]
        for key in TRAY_MACHINE_REQUIRED:
            assert key in ent, f"{mid} missing {key}"
    ionos = obj["machines"]["ionos"]
    assert ionos["weekly"] == 42
    assert ionos["jobs"][0]["sha"] == "abc1234"
    assert ionos["jobs"][0]["run_time"] == "5m"
    assert obj["machines"]["flamingo"]["weekly"] == 8
    assert obj["machines"]["flamingo"]["queued"] == 1
    raw = json.dumps(obj)
    assert "password=" not in raw.lower()
    assert "xai_api_key=" not in raw.lower()


def test_digest_json_chunk_reassembly_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(bobreport, "MAX_DIGEST_LINE", 120)
    bobreport.apply_callback(
        tmp_path,
        {
            "op": "merge",
            "machine": "ionos",
            "weekly": 33,
            "period_end": "2026-09-28T00:00:00Z",
            "pcent": {"cursor-models": 44, "other-models": 22, "grok-weekly": 11},
            "jobs": [
                {
                    "repo": "SimonBarnett/agentic_irc",
                    "sha": "deadbeef",
                    "model": "composer-2.5",
                    "description": "chunk reassembly coverage",
                    "state": "running",
                    "run_time": "3m",
                }
            ],
        },
    )
    bobstat.write_peer(
        tmp_path,
        {
            "ok": True,
            "id": "flamingo",
            "weekly": 9,
            "running": 1,
            "queued": 0,
            "lastSeen": "2026-09-21T12:00:00Z",
            "jobs": [{"repo": "SimonBarnett/agentic_build", "state": "queued"}],
        },
    )
    lines = bobreport.format_digest_whisper_lines(
        tmp_path, "Jeeves", form="full", english=False
    )
    digest_lines = [ln for ln in lines if ln.startswith("BOB DIGEST v1 ")]
    assert len(digest_lines) >= 2
    obj = _digest_json_from_whisper(lines)
    assert obj["chairNick"]
    assert len(obj["cursor_pools"]) >= 1
    assert obj["machines"]["ionos"]["jobs"][0]["run_time"] == "3m"


def test_format_digest_whisper_tray_keys_and_chunks(tmp_path):
    bobreport.apply_callback(
        tmp_path,
        {
            "op": "merge",
            "machine": "marchhare",
            "pcent": {"cursor-models": 12},
            "weekly": 4,
            "period_end": "2026-09-30T00:00:00Z",
        },
    )
    agent_lines = bobreport.format_digest_whisper_lines(
        tmp_path, "Jeeves", form="full", english=False
    )
    assert agent_lines
    assert not any("I am offline" in x and x.startswith("flamingo") for x in agent_lines)
    obj = _digest_json_from_whisper(agent_lines)
    assert "cursor_pools" in obj
    assert len(obj["cursor_pools"]) >= 1
    human_lines = bobreport.format_digest_whisper_lines(tmp_path, "Jeeves", form="full", english=True)
    assert any("I am offline" in x or "I am online" in x for x in human_lines)
    assert _digest_json_from_whisper(human_lines)


def test_cursor_pools_from_pcent_when_not_stored(tmp_path):
    bobreport.apply_callback(
        tmp_path,
        {
            "op": "merge",
            "machine": "ce-priority-dev1",
            "pcent": {"cursor-models": 77},
            "cursor_label": "Dev1 seat",
            "period_end": "2026-09-28T00:00:00Z",
        },
    )
    obj = bobreport.build_digest_object(tmp_path, "bob-dev1")
    pools = obj["cursor_pools"]
    assert pools
    models = next(p for p in pools if p.get("id") == "cursor-models")
    assert models["remaining"] == 77
    assert models["label"] == "Cursor Models"
    assert models["seat"] == "cursor-models"
    assert models["period_end"] is None
    assert models["reset"] is None


def test_cursor_pools_weekly_vs_cursor_period_and_peer_pcent(tmp_path):
    weekly_end = "2026-09-28T00:00:00Z"
    cursor_end = "2026-10-16T00:00:00Z"
    bobreport.apply_callback(
        tmp_path,
        {
            "op": "merge",
            "machine": "ionos",
            "weekly": 42,
            "period_end": weekly_end,
            "reset": weekly_end,
            "pcent": {"cursor-models": 55},
            "cursor_period_end": cursor_end,
            "cur": "-£75.03",
        },
    )
    bobstat.write_peer(
        tmp_path,
        {
            "ok": True,
            "id": "flamingo",
            "weekly": 8,
            "period_end": "2026-09-30T00:00:00Z",
            "pcent": {"cursor-models": 12},
            "cursor_period_end": cursor_end,
            "cur": "12%",
        },
    )
    obj = bobreport.build_digest_object(tmp_path, "Jeeves")
    for pool in obj["cursor_pools"]:
        assert pool.get("period_end") != weekly_end
        assert pool.get("reset") != weekly_end
        assert pool.get("overage") not in ("12%", "-£75.03")

    ionos = obj["machines"]["ionos"]
    assert ionos["period_end"] == weekly_end
    assert ionos["cursor_period_end"] == cursor_end
    models_pool = next(p for p in obj["cursor_pools"] if p.get("id") == "cursor-models")
    assert models_pool["period_end"] == cursor_end
    assert models_pool["reset"] == cursor_end
    assert models_pool["remaining"] == 12
    assert models_pool.get("overage") is None
    assert models_pool["seat"] == "cursor-models"

    flamingo = obj["machines"]["flamingo"]
    assert flamingo.get("cursor_period_end") == cursor_end
    assert flamingo.get("cur") == "12%"


def test_cursor_pools_official_groups_reject_xai_seat_labels(tmp_path):
    bobreport.apply_callback(
        tmp_path,
        {
            "op": "merge",
            "machine": "marchhare",
            "pcent": {"cursor-models": 40, "other-models": 22, "grok-weekly": 88},
            "cursor_label": "Smart Catalogue",
        },
    )
    doc = bobreport.load_digest(tmp_path)
    doc["cursor_pools"] = [
        {"id": "ionos", "label": "Club Madeira", "remaining": 10},
        {"id": "ntsa", "label": "ntsa", "remaining": 5},
        {
            "group": "cursor-models",
            "label": "Smart Catalogue",
            "remaining": 99,
        },
    ]
    bobreport.save_digest(tmp_path, doc)
    obj = bobreport.build_digest_object(tmp_path, "Jeeves")
    pools = obj["cursor_pools"]
    ids = {p["id"] for p in pools}
    labels = {p["label"] for p in pools}
    assert "ionos" not in ids
    assert "ntsa" not in ids
    assert "Smart Catalogue" not in labels
    assert "Club Madeira" not in labels
    assert "ntsa" not in labels
    assert "cursor-models" in ids
    assert labels.intersection({"Cursor Models", "Other Models", "Grok Weekly"})
    models = next(p for p in pools if p["id"] == "cursor-models")
    assert models["label"] == "Cursor Models"
    assert models["remaining"] == 40
