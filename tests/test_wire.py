from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import seal
import wire


def test_capa_happy():
    p = wire.parse_capa_line(
        "CAPA v1 dumb nick=srv2012-box verbs=ping,sysinfo,exec,get,put psk=1 agpk=0 jail=C:\\agent-drop"
    )
    assert p is not None
    assert p.nick == "srv2012-box"
    assert "exec" in p.verbs
    assert p.psk == "1"


def test_capa_missing_verbs():
    assert wire.parse_capa_line("CAPA v1 dumb nick=x") is None


def test_moot_open_join():
    mid = "0123456789abcdef"
    o = wire.parse_moot_line(f"MOOT v1 OPEN {mid} grok-box-a floor :cut over file server")
    assert o is not None and o.verb == "OPEN" and o.text.startswith("cut")
    j = wire.parse_moot_line(f"MOOT v1 JOIN {mid}")
    assert j is not None and j.verb == "JOIN"


def test_moot_lowercase_verb_fails():
    assert wire.parse_moot_line("MOOT v1 open 0123456789abcdef grok-box-a floor :x") is None


def test_moot_missing_v1():
    assert wire.parse_moot_line("MOOT OPEN 0123456789abcdef grok-box-a floor :x") is None


def test_file_offer_pathlike_name():
    mid = "0123456789abcdef"
    assert wire.parse_file_line(f"FILE v1 OFFER bob alice {mid} 10 abc tier M ./x") is None
    assert wire.parse_file_line(f"FILE v1 OFFER bob alice {mid} 10 abcdef S backup.ps1") is not None


def test_dumb_n_too_large():
    line = "DUMB v1 bob alice 0123456789abcdef 1 100 " + "A" * 10
    assert wire.parse_dumb_line(line) is None


def test_seal_v2_still_only_seal_parser():
    line = "SEAL v2 bob alice 0123456789abcdef 1 1 QUJD"
    assert seal.parse_seal_line(line) is not None
    assert wire.parse_moot_line(line) is None
    assert wire.parse_capa_line(line) is None
