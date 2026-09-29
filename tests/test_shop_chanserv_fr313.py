"""FR #313: bob-* REGISTER #{machine} with ChanServ."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import shop_chanserv  # noqa: E402


def test_chanserv_register_line():
    assert shop_chanserv.chanserv_register_line("#ionos") == "PRIVMSG ChanServ :REGISTER #ionos"
    assert shop_chanserv.chanserv_register_line("#ce-priority-dev1") == (
        "PRIVMSG ChanServ :REGISTER #ce-priority-dev1"
    )


def test_chanserv_register_rejects_smuggle():
    line = shop_chanserv.chanserv_register_line("#ionos\r\nPRIVMSG #bobiverse :x")
    assert "\r" not in line and "\n" not in line
    assert line == "PRIVMSG ChanServ :REGISTER #ionos"


def test_should_register_shop_bob_only():
    assert shop_chanserv.should_register_shop("bob-ionos", ["#bobiverse", "#ionos"]) == "#ionos"
    assert shop_chanserv.should_register_shop("bob-flamingo", ["#flamingo"]) == "#flamingo"
    assert shop_chanserv.should_register_shop("ionos-14020", ["#ionos"]) is None
    assert shop_chanserv.should_register_shop("w-io-99", ["#ionos"]) is None
    assert shop_chanserv.should_register_shop("bob-ionos", ["#bobiverse"]) is None


def test_register_lines_for_bob():
    lines = shop_chanserv.register_lines_for_bob("bob-ionos", ["#bobiverse", "#ionos"])
    assert lines == ["PRIVMSG ChanServ :REGISTER #ionos"]
    assert shop_chanserv.register_lines_for_bob("console-ionos", ["#ionos"]) == []


def test_nickserv_lines_and_password_mint(tmp_path: Path):
    assert shop_chanserv.nickserv_register_identify_lines("bob-ionos", "secret", "bob@ionos.local") == [
        "PRIVMSG NickServ :IDENTIFY bob-ionos secret",
        "PRIVMSG NickServ :REGISTER secret bob@ionos.local",
    ]
    pw = shop_chanserv.ensure_bob_nickserv_password(tmp_path, mint=True)
    assert pw and len(pw) >= 8
    assert (tmp_path / "nickserv.password").is_file()
    assert shop_chanserv.ensure_bob_nickserv_password(tmp_path, mint=False) == pw


def test_ionos_operator_runbook_exists():
    """Operator checklist for enabling Ergo ChanServ (ionos action)."""
    doc = ROOT / "docs" / "ergo-chanserv-enable-bob-shops.md"
    text = doc.read_text(encoding="utf-8")
    assert "channels:" in text
    assert "registration:" in text
    assert "enabled: true" in text
    assert "Restart-Service BobIrcd" in text
    assert "INFO chanserv REGISTER" in text
    assert "FR #313" in text or "#313" in text
    bob_irc = (ROOT / ".grok" / "skills" / "bob-irc" / "SKILL.md").read_text(encoding="utf-8")
    assert "ergo-chanserv-enable-bob-shops.md" in bob_irc
