"""FR #236: offline acceptance stubs for DUMB service shape."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_fr236_design_doc_exists():
    p = ROOT / "docs" / "dumb-service-fr236.md"
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    assert "LocalSystem" in text
    assert "account-bound" in text.lower() or "account-notify" in text
    assert "DPAPI" in text


def test_fr236_skill_mentions_service():
    skill = ROOT / ".grok" / "skills" / "agentic-dumb" / "SKILL.md"
    assert skill.is_file()
    text = skill.read_text(encoding="utf-8")
    assert "FR #236" in text or "service" in text.lower()


def test_fr236_account_map_available_for_service():
    # Service must consume FR #230 account map helpers.
    import account_map as am

    assert hasattr(am, "AccountMap")
    assert "account-notify" in am.ACCOUNT_CAPS
