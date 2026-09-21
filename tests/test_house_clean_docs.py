from __future__ import annotations

import re
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_readme_and_bob_irc_fleet_host():
    root = _repo_root()
    readme = (root / "README.md").read_text(encoding="utf-8")
    bob_irc = (root / ".grok" / "skills" / "bob-irc" / "SKILL.md").read_text(encoding="utf-8")
    for text in (readme, bob_irc):
        assert "irc.ntsa.uk" in text
        assert "#bobiverse" in text
    assert "## Legacy Libera" in readme


def test_bob_irc_does_not_send_bob_nicks_to_libera():
    root = _repo_root()
    text = (root / ".grok" / "skills" / "bob-irc" / "SKILL.md").read_text(encoding="utf-8")
    # Must warn against Libera for fleet nicks, not instruct bob-* there.
    assert re.search(r"bob-\*.*Libera", text, re.I)
    assert not re.search(r"join.*Libera.*bob-", text, re.I)
    assert "ce-priority-dev1" in text


def test_docs_index_and_tofu_runbook_exist():
    root = _repo_root()
    index = (root / "docs" / "README.md").read_text(encoding="utf-8")
    assert "mrb-" in index and "audit" in index.lower()
    assert "shop-channel-worker-cc-webhook" in index
    tofu = (root / "docs" / "tofu-rotation.md").read_text(encoding="utf-8")
    assert "peers.json" in tofu


def test_bob_irc_scrubs_report_write_path():
    root = _repo_root()
    text = (root / ".grok" / "skills" / "bob-irc" / "SKILL.md").read_text(encoding="utf-8")
    assert "Do **not** implement `!report`" in text or "no `!report`" in text.lower() or "No `!report`" in text
    assert "!bobiverse" in text
    assert "w-<shortid>-<pid>" in text or "w-<short>-<pid>" in text
    assert "GET digest" in text or "HTTP GET" in text


def test_dumb_skills_not_git_workers():
    root = _repo_root()
    needle = "git-task worker"
    for rel in (
        ".grok/skills/agentic-dumb/SKILL.md",
        ".grok/skills/invite-airc/SKILL.md",
        "README.md",
    ):
        text = (root / rel).read_text(encoding="utf-8").lower()
        assert needle in text
