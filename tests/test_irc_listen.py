from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import irc_listen
import install_skill as inst


def test_keeps_english_ack():
    raw = (
        ":bob-ionos!~u@x.irc PRIVMSG #bobiverse :"
        "@cursor-flamingo ionos here. weekly=0 (cannot grok-talk)."
    )
    out = irc_listen.format_talk_line(raw)
    assert out is not None
    assert out.startswith("FROM bob-ionos #bobiverse ")
    assert "ionos here" in out


def test_keeps_query():
    raw = ":bob-ionos!~u@x.irc PRIVMSG cursor-flamingo :pong from Query"
    assert irc_listen.format_talk_line(raw) == (
        "FROM bob-ionos cursor-flamingo pong from Query"
    )


def test_drops_point_ping_numeric():
    assert irc_listen.format_talk_line(
        ":bob-dev1!~u@x.irc PRIVMSG #bobiverse :MOOT v1 POINT b0b1be15e0000001 :idle"
    ) is None
    assert irc_listen.format_talk_line("PING cursor-flamingo") is None
    assert irc_listen.format_talk_line(":irc.ntsa.uk 001 cursor-flamingo :welcome") is None
    assert irc_listen.format_talk_line(
        ":bob-ionos!~u@x.irc PRIVMSG #bobiverse :AGPK v1 abc"
    ) is None


def test_install_skill_scripts_include_irc_listen():
    root = Path(__file__).resolve().parents[1]
    assert "irc_listen.py" in inst.SCRIPTS
    assert (root / "scripts" / "irc_listen.py").is_file()
