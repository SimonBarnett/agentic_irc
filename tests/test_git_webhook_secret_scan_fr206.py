"""FR #206: git webhook secret filter scans announce line only; redact title; log 4xx."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bobcallback
import bobreport


def _issues_opened_body(*, title: str, body: str, number: int = 327) -> bytes:
    return json.dumps(
        {
            "action": "opened",
            "issue": {
                "number": number,
                "title": title,
                "body": body,
            },
            "repository": {"full_name": "SimonBarnett/agentic_build"},
            "sender": {"login": "SimonBarnett"},
        }
    ).encode()


def test_issue_body_mentions_connect_password_still_204_with_title(tmp_path, capsys):
    """Body may mention connect.password (docs file name); announce keeps title."""
    allow = {"127.0.0.1"}
    body = _issues_opened_body(
        title="FR: turn on Ergo channel registration",
        body="same handling as connect.password path under ~/.grok/ergo/",
        number=327,
    )
    code, payload = bobcallback.handle_request(
        "POST",
        "/bob/v1/git",
        {"X-GitHub-Event": "issues"},
        body,
        "127.0.0.1",
        tmp_path,
        "",
        allow,
    )
    assert code == 204 and payload == b""
    chair = (tmp_path / "chair-outbox.txt").read_text(encoding="utf-8")
    assert "GIT issues SimonBarnett/agentic_build opened #327" in chair
    assert "FR: turn on Ergo channel registration" in chair
    assert "connect.password" not in chair  # body never announced
    assert "by SimonBarnett" in chair


def test_title_with_password_eq_redacted_204_no_secret_in_outbox_or_logs(tmp_path, capsys):
    allow = {"127.0.0.1"}
    secret_title = "leak password=super-secret-value-xyz"
    body = _issues_opened_body(
        title=secret_title,
        body="harmless body",
        number=99,
    )
    code, payload = bobcallback.handle_request(
        "POST",
        "/bob/v1/git",
        {"X-GitHub-Event": "issues"},
        body,
        "127.0.0.1",
        tmp_path,
        "",
        allow,
    )
    assert code == 204 and payload == b""
    chair = (tmp_path / "chair-outbox.txt").read_text(encoding="utf-8")
    assert "GIT issues" in chair
    assert "opened #99" in chair
    assert "title redacted" in chair
    assert "super-secret-value-xyz" not in chair
    assert "password=" not in chair
    out = capsys.readouterr().out
    assert "super-secret-value-xyz" not in out
    assert "password=super" not in out


def test_malformed_json_and_missing_event_still_400_and_logged(tmp_path, capsys):
    allow = {"127.0.0.1"}
    code, _ = bobcallback.handle_request(
        "POST",
        "/bob/v1/git",
        {},
        b'{"repository":{"full_name":"x/y"}}',
        "127.0.0.1",
        tmp_path,
        "",
        allow,
    )
    assert code == 400
    out = capsys.readouterr().out
    assert "INFO git webhook reject" in out
    assert "reason=no event" in out

    code2, _ = bobcallback.handle_request(
        "POST",
        "/bob/v1/git",
        {"X-GitHub-Event": "issues"},
        b"{not-json",
        "127.0.0.1",
        tmp_path,
        "",
        allow,
    )
    assert code2 == 400
    out2 = capsys.readouterr().out
    assert "reason=invalid json" in out2


def test_redact_helper_strips_marker_from_announce_line():
    line = (
        "GIT issues SimonBarnett/agentic_build opened #1 "
        "bad password=xyz title by simon"
    )
    red = bobreport.redact_git_announce_line(line)
    assert red.startswith("GIT issues")
    assert "opened #1" in red
    assert "title redacted" in red
    assert "xyz" not in red
    assert not bobreport.looks_like_secret(red)
