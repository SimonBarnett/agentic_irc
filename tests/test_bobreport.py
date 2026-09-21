from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bobreport


def test_report_help_whisper_text():
    out = bobreport.apply_report(Path("/tmp/x"), "bob-ionos", "bob-flamingo", "!report ?")
    assert out.ok and out.help_text == bobreport.HELP_TEXT


def test_refuse_secret():
    out = bobreport.apply_report(
        Path("/tmp/x"), "bob-ionos", "bob-flamingo", "!report PCENT ionos cursor-models 50 password=leak"
    )
    assert not out.ok and out.err and "secret" in out.err.lower()


def test_task_start_stop_and_pcent_digest(tmp_path):
    home = tmp_path
    o1 = bobreport.apply_report(
        home,
        "bob-flamingo",
        "bob-ionos",
        "!report TASK START SimonBarnett/agentic_build 8d9a852 composer-2.5 house-clean docs 12m",
    )
    assert o1.ok and o1.speak_channel and "started" in o1.speak_channel
    o2 = bobreport.apply_report(
        home,
        "bob-dev1",
        "bob-ionos",
        "!report TASK START SimonBarnett/agentic_irc abcdef1 grok issue-36 work 5m",
    )
    assert o2.ok
    o3 = bobreport.apply_report(home, "bob-ionos", "bob-ionos", "!report PCENT flamingo cursor-models 12")
    assert o3.ok
    o4 = bobreport.apply_report(home, "bob-ionos", "bob-ionos", "!report PCENT dev1 grok-build 8")
    assert o4.ok
    obj = bobreport.build_digest_object(home, "bob-ionos")
    assert "flamingo" in obj["machines"]
    assert obj["machines"]["ce-priority-dev1"]["pcent"]["grok-build"] == 8
    assert obj["machines"]["flamingo"]["pcent"]["cursor-models"] == 12
    assert obj["machines"]["flamingo"]["task"]["state"] == "START"
    lines = bobreport.format_digest_whisper_lines(home, "bob-ionos")
    assert lines
    if len(lines) == 1:
        parsed = json.loads(lines[0])
        assert parsed["v"] == 1


def test_pcent_duplicate_no_speak_flag(tmp_path):
    home = tmp_path
    bobreport.apply_report(home, "bob-ionos", "bob-ionos", "!report PCENT ionos cursor-models 50")
    out = bobreport.apply_report(home, "bob-ionos", "bob-ionos", "!report PCENT ionos cursor-models 50")
    assert out.ok and out.speak_channel is None


def test_bad_machine_id(tmp_path):
    out = bobreport.apply_report(tmp_path, "bob-ionos", "bob-ionos", "!report PCENT NOPE cursor-models 50")
    assert not out.ok and "machine" in (out.err or "").lower()


def test_uptime_scoped_to_sender(tmp_path):
    out = bobreport.apply_report(tmp_path, "bob-marchhare", "bob-ionos", "!report UPTIME 2026-09-20")
    assert out.ok
    doc = bobreport.load_digest(tmp_path)
    assert doc["machines"]["marchhare"]["uptime_since"].startswith("2026-09-20")


def test_malformed_task(tmp_path):
    out = bobreport.apply_report(tmp_path, "bob-ionos", "bob-ionos", "!report TASK START only-three tokens")
    assert not out.ok and out.err and out.err.startswith("ERR report")
