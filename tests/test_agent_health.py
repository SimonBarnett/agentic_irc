from __future__ import annotations

import json
import subprocess
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
    assert ah.session_store_path("aider").name.endswith("aider.session")


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


def test_format_aider_wake_payload():
    body = ah.format_aider_wake_payload(["FROM simon #marchhare ping"], sink_name="listen.stdout.log")
    assert "listen.stdout.log" in body
    assert "FROM simon #marchhare ping" in body
    assert "Do not exit the REPL" in body
    assert not ah.wake_prompt_includes_boot_skills(body)


def test_commit_offset_only_after_successful_wake():
    assert ah.commit_listen_offset_after_wake(
        agent_started=False, exit_code=0, current_offset=0, next_offset=99
    ) == 0
    assert ah.commit_listen_offset_after_wake(
        agent_started=True, exit_code=0, current_offset=0, next_offset=99
    ) == 99
