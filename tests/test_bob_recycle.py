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


def test_default_watch_is_stop_then_one_start(monkeypatch, tmp_path):
    runs: list[str] = []
    pops: list[list[str]] = []
    kills: list[str] = []

    monkeypatch.setattr(bob_recycle.os, "name", "nt")
    monkeypatch.setattr(bob_recycle, "_win_kill_matching_ps1", lambda n: kills.append(n) or [])
    monkeypatch.setattr(bob_recycle, "_win_process_commandlines", lambda _s: [])

    def fake_run(cmd, **_k):
        text = " ".join(str(x) for x in cmd)
        runs.append(text)
        class R:
            returncode = 1 if "Start-ScheduledTask" in text else 0
        return R()

    def fake_popen(cmd, **_k):
        pops.append([str(x) for x in cmd])
        return object()

    monkeypatch.setattr(bob_recycle.subprocess, "run", fake_run)
    monkeypatch.setattr(bob_recycle.subprocess, "Popen", fake_popen)
    wrap = tmp_path / "tools"
    wrap.mkdir()
    script = wrap / "_Watch-Bobiverse-flamingo.ps1"
    script.write_text("# wrap\n", encoding="utf-8")
    (wrap / "Watch-BobTray.ps1").write_text("# tray\n", encoding="utf-8")
    bob_recycle._default_restart_watch(tmp_path, "flamingo")
    assert any("Stop-ScheduledTask" in x for x in runs)
    assert any("Start-ScheduledTask" in x for x in runs)
    assert any("Watch-Bobiverse" in x for x in kills)
    assert len(pops) == 1
    assert any("_Watch-Bobiverse-flamingo.ps1" in x for x in pops[0])
    assert not any("Watch-BobJobs" in " ".join(x) for x in pops)
    assert not any("BobFleet" in r for r in runs)


def test_default_tray_kills_old_and_starts_once(monkeypatch, tmp_path):
    pops: list[list[str]] = []
    killed: list[str] = []
    monkeypatch.setattr(bob_recycle.os, "name", "nt")
    monkeypatch.setattr(bob_recycle, "_win_kill_matching_ps1", lambda n: killed.append(n) or [11])
    monkeypatch.setattr(bob_recycle.time, "sleep", lambda _s: None)

    def fake_popen(cmd, **_k):
        pops.append([str(x) for x in cmd])
        return object()

    monkeypatch.setattr(bob_recycle.subprocess, "Popen", fake_popen)
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "Watch-BobTray.ps1").write_text("# tray\n", encoding="utf-8")
    bob_recycle._default_recycle_tray(tmp_path)
    assert killed == ["Watch-BobTray.ps1"]
    assert len(pops) == 1
    assert any("Watch-BobTray.ps1" in x for x in pops[0])


def test_default_chair_does_not_wait_on_self(monkeypatch, tmp_path):
    pops: list[list[str]] = []
    waited = []

    def boom(*_a, **_k):
        waited.append(True)
        raise AssertionError("must not graceful_stop_agent")

    monkeypatch.setattr(bob_recycle.os, "name", "nt")
    monkeypatch.setattr(bob_recycle.subprocess, "Popen", lambda cmd, **_k: pops.append([str(x) for x in cmd]) or object())
    import agent_control

    monkeypatch.setattr(agent_control, "graceful_stop_agent", boom)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "Install-BobChair.ps1").write_text("# install\n", encoding="utf-8")
    (scripts / "bobcallback.py").write_text("# cb\n", encoding="utf-8")
    monkeypatch.setattr(bob_recycle, "find_agentic_irc_root", lambda: tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    bob_recycle._default_restart_chair(tmp_path, home)
    assert waited == []
    assert len(pops) == 1
    helper = home / "recycle-chair-after-exit.ps1"
    assert helper.is_file()
    text = helper.read_text(encoding="utf-8")
    assert "$agentHome =" in text
    assert "Install-BobChair.ps1" in text
    assert "bobcallback.py" in text
    assert "Get-Process -Id $waitPid" in text
    assert "--home',$agentHome" in text or "--home,$agentHome" in text


def test_chair_helper_agent_home_executes_under_powershell(monkeypatch, tmp_path):
    import shutil
    import subprocess

    real_popen = subprocess.Popen
    monkeypatch.setattr(bob_recycle.os, "name", "nt")
    monkeypatch.setattr(bob_recycle.subprocess, "Popen", lambda *_a, **_k: object())
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "Install-BobChair.ps1").write_text("# install\n", encoding="utf-8")
    (scripts / "bobcallback.py").write_text("# cb\n", encoding="utf-8")
    home = tmp_path / "agent-home"
    home.mkdir()
    bob_recycle._default_restart_chair(tmp_path, home)
    helper = home / "recycle-chair-after-exit.ps1"
    assigns = [
        ln
        for ln in helper.read_text(encoding="utf-8").splitlines()
        if ln.startswith("$agentHome") or ln.startswith("$install") or ln.startswith("$callback") or ln.startswith("$scripts")
    ]
    probe = tmp_path / "probe-agent-home.ps1"
    probe.write_text("\n".join(assigns) + "\nWrite-Output $agentHome\n", encoding="utf-8")
    exe = shutil.which("powershell.exe") or shutil.which("pwsh")
    if not exe:
        import pytest

        pytest.skip("powershell.exe not on PATH")
    monkeypatch.setattr(bob_recycle.subprocess, "Popen", real_popen)
    out = subprocess.check_output([exe, "-NoProfile", "-File", str(probe)], text=True)
    want = str(home.resolve())
    assert want in out
    assert out.strip().splitlines()[-1].strip() == want


def test_refuse_never_calls_kill_or_popen(monkeypatch):
    pops: list = []
    monkeypatch.setattr(bob_recycle.subprocess, "Popen", lambda *a, **k: pops.append(a) or object())
    monkeypatch.setattr(bob_recycle, "_win_kill_matching_ps1", lambda n: pops.append(("kill", n)) or [])
    assert bob_recycle.parse_recycle_query("!recycle nope") == ("refuse", "nope")
    assert pops == []
