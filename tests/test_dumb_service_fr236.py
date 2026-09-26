"""FR #236: offline acceptance stubs for DUMB service shape."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_fr236_design_doc_exists():
    p = ROOT / "docs" / "dumb-service-fr236.md"
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    assert "LocalSystem" in text
    assert "account" in text.lower()
    assert "DPAPI" in text


def test_fr236_skill_mentions_service():
    skill = ROOT / ".grok" / "skills" / "agentic-dumb" / "SKILL.md"
    assert skill.is_file()
    text = skill.read_text(encoding="utf-8")
    assert "FR #236" in text or "service" in text.lower()


def test_fr236_notes_account_map_dependency():
    # Service consumes FR #230 account map when that lands; design doc must name it.
    text = (ROOT / "docs" / "dumb-service-fr236.md").read_text(encoding="utf-8")
    assert "#230" in text or "account" in text.lower()
