from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import agent_health as ah


def test_session_store_path_cursor_grok(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(ah.Path, "home", lambda: tmp_path)
    p = ah.session_store_path("cursor")
    assert p == tmp_path / ".grok" / "bob-bridge" / "watch-agent-health-cursor.session"
    assert ah.session_store_path("grok").name.endswith("grok.session")


def test_read_write_session_id(tmp_path: Path):
    p = tmp_path / "s.session"
    assert ah.read_session_id(p) is None
    ah.write_session_id(p, "abc-123")
    assert ah.read_session_id(p) == "abc-123"


def test_filter_from_lines_drops_noise():
    chunk = "PING x\nFROM simon simon ping\n:server 001 nick\nFROM bob bob hi\n"
    assert ah.filter_from_lines(chunk) == [
        "FROM simon simon ping",
        "FROM bob bob hi",
    ]


def test_read_new_from_lines_offset(tmp_path: Path):
    log = tmp_path / "listen.stdout.log"
    log.write_text("FROM a a one\n", encoding="utf-8")
    lines, off = ah.read_new_from_lines(log, 0)
    assert lines == ["FROM a a one"]
    log.write_text("FROM a a one\nFROM b b two\n", encoding="utf-8")
    lines2, off2 = ah.read_new_from_lines(log, off)
    assert lines2 == ["FROM b b two"]
    assert off2 == log.stat().st_size


def test_evaluate_irc_tsr_healthy_and_stale():
    now = datetime(2026, 9, 22, 12, 0, 0, tzinfo=timezone.utc)
    ok = ah.evaluate_irc_tsr(
        agent_pid=1,
        listen_pid=2,
        nick="flamingo-1",
        agent_alive=True,
        listen_alive=True,
        log_exists=True,
        log_mtime_utc=now - timedelta(seconds=30),
        stale_seconds=900,
        now_utc=now,
    )
    assert ok.healthy
    bad = ah.evaluate_irc_tsr(
        agent_pid=1,
        listen_pid=2,
        nick="flamingo-1",
        agent_alive=True,
        listen_alive=False,
        log_exists=True,
        log_mtime_utc=now,
        stale_seconds=900,
        now_utc=now,
    )
    assert not bad.healthy
    stale = ah.evaluate_irc_tsr(
        agent_pid=1,
        listen_pid=2,
        nick="flamingo-1",
        agent_alive=True,
        listen_alive=True,
        log_exists=True,
        log_mtime_utc=now - timedelta(seconds=1000),
        stale_seconds=900,
        now_utc=now,
    )
    assert stale.log_stale and not stale.healthy


def test_coordinator_pids_parses():
    text = "nick=flamingo-9\nseat=9\nlisten=11\nagent=22\n"
    assert ah.coordinator_pids(text) == (22, 11, "flamingo-9")


def test_format_wake_payload():
    body = ah.format_irc_wake_payload(["FROM simon simon ping"], sink_name="listen-tsr.log")
    assert "listen-tsr.log" in body
    assert "FROM simon simon ping" in body
    assert not ah.wake_prompt_includes_boot_skills(body)


def test_parse_cursor_session_id_from_json():
    sample = (
        '{"type":"result","session_id":"09953f17-c3c5-42e2-a15c-f973dff51cdb",'
        '"result":"OK"}\n'
    )
    assert ah.parse_cursor_session_id(sample) == "09953f17-c3c5-42e2-a15c-f973dff51cdb"
    assert not ah.is_bound_cursor_session_id("not-a-cursor-id", None)
    fixture = (
        Path(__file__).resolve().parent / "fixtures" / "cursor_agent_boot_sample.jsonl"
    )
    captured = fixture.read_text(encoding="utf-8")
    assert ah.parse_cursor_session_id(captured) == "09953f17-c3c5-42e2-a15c-f973dff51cdb"


def test_invented_guid_without_bound_marker_is_not_bound(tmp_path: Path):
    invented = "00000000-0000-0000-0000-000000000001"
    session_path = tmp_path / "watch-agent-health-cursor.session"
    ah.write_session_id(session_path, invented)
    assert not ah.is_bound_cursor_session_id(invented, session_path)
    assert ah.cursor_boot_required(session_path) is True
    ah.write_cursor_bound_session(session_path, invented)
    assert ah.is_bound_cursor_session_id(invented, session_path)
    assert ah.cursor_boot_required(session_path) is False
    assert ah.cursor_wake_argv_includes_resume(session_path) is True


def test_commit_offset_only_after_successful_wake():
    assert ah.commit_listen_offset_after_wake(
        agent_started=False, exit_code=0, current_offset=0, next_offset=99
    ) == 0
    assert ah.commit_listen_offset_after_wake(
        agent_started=True, exit_code=1, current_offset=0, next_offset=99
    ) == 0
    assert ah.commit_listen_offset_after_wake(
        agent_started=True, exit_code=0, current_offset=0, next_offset=99
    ) == 99


def test_listen_sink_fallback_prefers_fresher_tsr_log(tmp_path: Path):
    home = tmp_path / "seat"
    home.mkdir()
    stdout = home / "listen.stdout.log"
    tsr = home / "listen-tsr.log"
    stdout.write_text("old\n", encoding="utf-8")
    tsr.write_text("FROM x x hi\n", encoding="utf-8")
    old = datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp()
    new = datetime(2026, 9, 22, tzinfo=timezone.utc).timestamp()
    stdout.touch()
    tsr.touch()
    import os

    os.utime(stdout, (old, old))
    os.utime(tsr, (new, new))
    path, kind = ah.select_listen_poll_sink(home)
    assert kind == "tsr"
    assert path == tsr


def test_listen_health_uses_fallback_when_stdout_stale(tmp_path: Path):
    home = tmp_path / "seat"
    home.mkdir()
    stdout = home / "listen.stdout.log"
    tsr = home / "listen-tsr.log"
    stdout.write_text("stale\n", encoding="utf-8")
    tsr.write_text("FROM a a ping\n", encoding="utf-8")
    import os

    now = datetime(2026, 9, 22, 12, 0, 0, tzinfo=timezone.utc)
    stale_ts = (now - timedelta(hours=2)).timestamp()
    fresh_ts = now.timestamp()
    os.utime(stdout, (stale_ts, stale_ts))
    os.utime(tsr, (fresh_ts, fresh_ts))
    exists, stale, _mtime, path = ah.listen_health_sink(
        home, stale_seconds=900, now_utc=now
    )
    assert exists
    assert path == tsr
    assert not stale


def test_second_wake_payload_is_not_boot_prompt(tmp_path: Path):
    wake = ah.format_irc_wake_payload(["FROM simon simon ping"])
    assert not ah.wake_prompt_includes_boot_skills(wake)
    session_path = tmp_path / "watch-agent-health-cursor.session"
    ah.write_cursor_bound_session(
        session_path, "09953f17-c3c5-42e2-a15c-f973dff51cdb"
    )
    assert ah.cursor_boot_required(session_path) is False


def test_watch_script_uses_agent_health_sink_helpers():
    root = Path(__file__).resolve().parents[1]
    ps1 = (root / "scripts" / "Watch-AgentHealth.ps1").read_text(encoding="utf-8")
    assert "agent_health.py" in ps1
    assert "select-sink" in ps1
    assert "listen-health" in ps1
    assert "keeping listen offset for replay" in ps1
    assert "parse-cursor-session" in ps1
    cursor_boot = ps1.split("if ($AgentInfo.Engine -eq 'cursor')")[1].split("elseif ($id)")[0]
    assert "[guid]::NewGuid()" not in cursor_boot
    assert "password=" not in ps1.lower()
    assert "XAI_API_KEY" not in ps1


def test_listen_sink_candidates_include_fallbacks(tmp_path: Path):
    home = tmp_path / "h"
    home.mkdir()
    kinds = [k for k, _ in ah.listen_sink_candidates(home)]
    assert kinds == ["stdout", "tsr", "irc_log"]
