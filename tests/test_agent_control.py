from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import agent_control as ac  # noqa: E402


def test_quit_request_roundtrip(tmp_path: Path):
    home = tmp_path / "seat"
    home.mkdir()
    assert ac.peek_quit_request(home) is None
    ac.request_agent_quit(home, "recycle")
    assert ac.peek_quit_request(home) == "recycle"
    assert ac.consume_quit_request(home) == "recycle"
    assert ac.peek_quit_request(home) is None


def test_graceful_stop_no_agent(tmp_path: Path):
    home = tmp_path / "seat"
    home.mkdir()
    assert ac.graceful_stop_agent(home, wait_s=0.5)


def test_quit_request_readable_on_protected_home(tmp_path: Path):
    import protect

    home = tmp_path / "seat"
    home.mkdir()
    protect.protect_path(home)
    ac.request_agent_quit(home, "stop")
    assert ac.peek_quit_request(home) == "stop"
