"""Docs encoding: UTF-8 without BOM; no common mojibake sequences (FR #227).

PR #225 re-saved README as UTF-8-with-BOM after cp1252 mis-decode, turning
em-dashes into ``â€”``. Worker packs must write UTF-8 without BOM (see #226).
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# UTF-8 bytes of curly punctuation mis-read as Windows-1252, then re-encoded.
MOJIBAKE_MARKERS = (
    "â€”",  # em dash
    "â€“",  # en dash
    "â€™",  # right single quotation
    "â€˜",  # left single quotation
    "â€œ",  # left double quotation
    "â€\x9d",  # right double (partial forms vary)
    "â€¢",  # bullet
    "Ã©",  # é
    "Ã—",  # ×
    "ï»¿",  # U+FEFF as mojibake text
)

UTF8_BOM = b"\xef\xbb\xbf"


def _md_files() -> list[Path]:
    out: list[Path] = []
    for p in ROOT.rglob("*.md"):
        if ".git" in p.parts:
            continue
        # skip huge vendor if any
        if "node_modules" in p.parts:
            continue
        out.append(p)
    return sorted(out)


def test_readme_no_bom_and_has_real_em_dash_or_ascii():
    p = ROOT / "README.md"
    raw = p.read_bytes()
    assert not raw.startswith(UTF8_BOM), "README.md must be UTF-8 without BOM"
    text = raw.decode("utf-8")
    assert "â€”" not in text, "README still has mojibake em-dash"
    # After fix, recycle line should use Unicode em dash or plain hyphen
    assert "\u2014" in text or "recycle-after-merge" in text


@pytest.mark.parametrize("path", _md_files(), ids=lambda p: str(p.relative_to(ROOT)))
def test_markdown_utf8_no_bom_no_mojibake(path: Path):
    raw = path.read_bytes()
    assert not raw.startswith(UTF8_BOM), f"{path.relative_to(ROOT)} has UTF-8 BOM"
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        pytest.fail(f"{path.relative_to(ROOT)} is not valid UTF-8: {e}")
    for marker in MOJIBAKE_MARKERS:
        assert marker not in text, (
            f"{path.relative_to(ROOT)} contains mojibake {marker!r} "
            f"(re-save as UTF-8 without BOM; see FR #227)"
        )
