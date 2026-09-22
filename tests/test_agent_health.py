from __future__ import annotations

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
    body = ah.format_irc_wake_payload(["FROM simon simon ping"])
    assert "listen.stdout.log" in body
    assert "FROM simon simon ping" in body


def test_watch_script_present_and_polls_listen_log():
    root = Path(__file__).resolve().parents[1]
    ps1 = (root / "scripts" / "Watch-AgentHealth.ps1").read_text(encoding="utf-8")
    assert "listen.stdout.log" in ps1
    assert "Read-NewIrcFromLines" in ps1
    assert "watch-agent-health-" in ps1
    assert "--resume" in ps1
    assert "Start-IrcTsr.ps1" in ps1
    assert "password=" not in ps1.lower()
    assert "XAI_API_KEY" not in ps1
