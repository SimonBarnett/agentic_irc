from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bob_recycle
import bobtalk


def test_parse_recycle_query_valid_and_alias():
    assert bob_recycle.parse_recycle_query("!recycle ionos") == ("run", "ionos")
    assert bob_recycle.parse_recycle_query("!RECYCLE dev1") == ("run", "ce-priority-dev1")
    assert bob_recycle.parse_recycle_query("!recycle") == ("refuse", None)


def test_parse_recycle_query_refuse_unknown():
    assert bob_recycle.parse_recycle_query("!recycle nope") == ("refuse", "nope")
    assert bob_recycle.resolve_recycle_machine("nope") is None


def test_recycle_wire_roundtrip():
    assert bob_recycle.parse_recycle_wire("RECYCLE v1 flamingo") == "flamingo"
    assert bob_recycle.parse_recycle_wire("recycle v1 marchhare") == "marchhare"
    assert bob_recycle.format_recycle_wire("ionos") == "RECYCLE v1 ionos"


def test_build_plan_includes_tray_and_ionos_chair():
    plan = bob_recycle.build_recycle_plan("flamingo", ionos_chair=False)
    assert "recycle_watch_bobtray" in plan.steps
    assert "restart_bob_chair" not in plan.steps
    ionos = bob_recycle.build_recycle_plan("ionos", ionos_chair=True)
    assert "restart_bob_chair" in ionos.steps
    assert "restart_bobcallback" in ionos.steps


def test_execute_local_recycle_uses_hooks_no_subprocess():
    calls: list[str] = []

    hooks = bob_recycle.RecycleHooks(
        git_pull=lambda _p: calls.append("pull"),
        restart_watch=lambda _b, _m: calls.append("watch"),
        recycle_tray=lambda _b: calls.append("tray"),
        restart_chair=lambda _i, _h: calls.append("chair"),
        restart_callback=lambda _h, _i: calls.append("callback"),
    )
    plan = bob_recycle.execute_local_recycle("ionos", Path("/tmp/home"), ionos_chair=True, hooks=hooks)
    assert plan.machine_id == "ionos"
    assert calls == ["pull", "watch", "tray", "chair", "callback"]


def test_refuse_unknown_does_not_execute():
    calls: list[str] = []
    hooks = bob_recycle.RecycleHooks(git_pull=lambda _p: calls.append("pull"))
    assert bob_recycle.parse_recycle_query("!recycle xyzzy") == ("refuse", "xyzzy")
    assert calls == []


def test_protocol_line_recycle():
    assert bobtalk.parse_recycle_command("!recycle ionos")
    assert bobtalk.is_protocol_line("!recycle flamingo")
