"""Hostname shop id harvest (Simon 2026-09-29)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_bob_irc_hostname_shop_cast_iron():
    text = _read(".grok/skills/bob-irc/SKILL.md")
    assert "COMPUTERNAME" in text
    assert "win-mpre8vi4u6u" in text
    assert "You must be an oper on the channel" in text


def test_agentic_irc_hostname_shop_cast_iron():
    text = _read(".grok/skills/agentic-irc/SKILL.md")
    assert "COMPUTERNAME" in text
    assert "win-mpre8vi4u6u" in text
    assert "ionos" in text and "Do not invent" in text


def test_ergo_runbook_uses_hostname_example():
    text = _read("docs/ergo-chanserv-enable-bob-shops.md")
    assert "win-mpre8vi4u6u" in text
    assert "COMPUTERNAME" in text
