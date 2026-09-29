"""FR #322 / MRB fix for PR #324: workgroup lobby docs are UTF-8 no BOM and state the product call."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UTF8_BOM = b"\xef\xbb\xbf"
PATHS = (
    "docs/airc-console-domain-lobby.md",
    "docs/feature-request-airc-console-workgroup-lobby-2026-09-29.md",
    ".grok/skills/airc-console/SKILL.md",
)


def test_fr322_workgroup_lobby_docs_utf8_no_bom_and_decision() -> None:
    for rel in PATHS:
        raw = (ROOT / rel).read_bytes()
        assert not raw.startswith(UTF8_BOM), f"{rel} has UTF-8 BOM"
        text = raw.decode("utf-8")
        assert "FR #322" in text, f"{rel} missing FR #322"
        assert "#workgroup" in text, f"{rel} missing #workgroup"
    lobby = (ROOT / "docs/airc-console-domain-lobby.md").read_text(encoding="utf-8")
    assert "acceptable intentional shared lobby" in lobby
    assert "AIRC_CONSOLE_DOMAIN" in lobby
