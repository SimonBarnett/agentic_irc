from __future__ import annotations

from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _skill(rel: str) -> str:
    return (_repo_root() / rel).read_text(encoding="utf-8")


def test_skills_and_readme_lock_recycle_after_merge():
    readme = (_repo_root() / "README.md").read_text(encoding="utf-8")
    agentic = _skill(".grok/skills/agentic-irc/SKILL.md")
    bob = _skill(".grok/skills/bob-irc/SKILL.md")
    for text in (readme, agentic, bob):
        assert "recycle-after-merge" in text
        assert "PASS-nits" in text
        lower = text.lower()
        assert "ionos" in lower
        assert "restart" in lower and "irc" in lower
    for skill in (agentic, bob):
        assert "implementer" in skill.lower()
        assert "do not live-recycle" in skill.lower() or "do not live-recycle" in skill
