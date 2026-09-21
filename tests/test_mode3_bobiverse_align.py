from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import moot_thin_proto as thin

ROOT = Path(__file__).resolve().parents[1]


MODE3_DOC_PATHS = (
    "src/moot_thin/README.md",
    "docs/mode3-zero-config-2026-09-19.md",
    "docs/mode3-tls-spike.md",
    "docs/mode3-os-matrix.md",
)

SKILL_PATHS = (
    ".grok/skills/invite-airc/SKILL.md",
    ".grok/skills/agentic-dumb/SKILL.md",
    ".grok/skills/agentic-irc/SKILL.md",
)


def test_mode3_docs_ergo_first_not_libera_happy_path():
    for rel in MODE3_DOC_PATHS:
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "irc.ntsa.uk" in text
        low = text.lower()
        assert "join libera" not in low
        assert "live ergo" in low or "ergo" in low
    spike = (ROOT / "docs/mode3-tls-spike.md").read_text(encoding="utf-8")
    assert "legacy" in spike.lower() or "Libera" in spike


def test_mode3_skills_forbid_bobiverse_pairing_and_two_chairs():
    invite = (ROOT / ".grok/skills/invite-airc/SKILL.md").read_text(encoding="utf-8")
    low_inv = invite.lower()
    assert "#bobiverse" in invite
    assert "forbidden" in low_inv or "do not" in low_inv
    assert "irc.ntsa.uk" in invite
    assert "jeeves" in low_inv or "Jeeves" in invite
    assert "airc-moot-thin" in invite and "--chair" in invite

    for rel in (".grok/skills/agentic-dumb/SKILL.md", ".grok/skills/agentic-irc/SKILL.md"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        low = text.lower()
        assert "git-task worker" in low or "git worker" in low
        assert "jeeves" in low or "two chair" in low or "two chairs" in low
        assert "digest" in low or "!bobiverse" in low or "report" in low


def test_ini_example_forbids_bobiverse_pairing():
    ini = (ROOT / "src/moot_thin/airc-moot-thin.ini.example").read_text(encoding="utf-8")
    assert "irc.ntsa.uk" in ini
    assert "#bobiverse" in ini.lower() or "bobiverse" in ini.lower()
    assert "#airc-moot" in ini


def test_pairing_channel_bobiverse_refused():
    with pytest.raises(ValueError, match="bobiverse"):
        thin.validate_config(
            thin.ThinConfig(
                nick="m3-box",
                channel="#bobiverse",
                home=".",
                allow_path=".",
                pairing=True,
                pin="482917",
            )
        )


def test_main_default_hello_only_when_set():
    main = (ROOT / "src/moot_thin/main.c").read_text(encoding="utf-8")
    assert "if (cfg->hello[0])" in main
    assert re.search(r"say\(irc,\s*cfg->channel,\s*cfg->hello\)", main)


def test_chair_invite_includes_host():
    line = thin.chair_invite_line("482917", "#airc-moot", "0123456789abcdef")
    assert "--host irc.ntsa.uk" in line
