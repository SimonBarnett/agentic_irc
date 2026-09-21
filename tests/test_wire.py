from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import seal
import wire


MOOT_TABLE3 = (
    ("OPEN", "MOOT v1 OPEN 0123456789abcdef grok-box-a floor :cut over file server"),
    ("JOIN", "MOOT v1 JOIN 0123456789abcdef"),
    ("PART", "MOOT v1 PART 0123456789abcdef :bye"),
    ("HANDOFF", "MOOT v1 HANDOFF 0123456789abcdef claude-box"),
    ("FLOOR", "MOOT v1 FLOOR 0123456789abcdef grok-box-a"),
    ("SAY", "MOOT v1 SAY 0123456789abcdef 1 :hello"),
    ("POINT", "MOOT v1 POINT 0123456789abcdef :idle"),
    ("YIELD", "MOOT v1 YIELD 0123456789abcdef *"),
    ("ROLL", "MOOT v1 ROLL 0123456789abcdef"),
    ("ROSTER", "MOOT v1 ROSTER 0123456789abcdef :grok-box-a,claude-box"),
    ("CLOSE", "MOOT v1 CLOSE 0123456789abcdef :done"),
)


def test_w1_each_table3_verb():
    for verb, line in MOOT_TABLE3:
        p = wire.parse_moot_line(line)
        assert p is not None, verb
        assert p.verb == verb
        assert p.moot_id == "0123456789abcdef"


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


def test_moot_open_extra_tokens():
    assert wire.parse_moot_line("MOOT v1 OPEN 0123456789abcdef grok-box-a floor extra :x") is None


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
    assert wire.parse_file_line(line) is None
    assert wire.parse_dumb_line(line) is None


def test_tests_do_not_open_libera():
    root = Path(__file__).resolve().parent
    host = "irc.libera" + ".chat"
    for p in root.glob("test_*.py"):
        text = p.read_text(encoding="utf-8")
        assert host not in text
        if p.resolve() != Path(__file__).resolve():
            assert "create_connection" not in text


def test_production_default_host_is_private_ergo():
    root = Path(__file__).resolve().parents[1]
    host = "irc.ntsa.uk"
    agent = (root / "scripts" / "irc_agent.py").read_text(encoding="utf-8")
    dumb = (root / "scripts" / "dumb_agent.py").read_text(encoding="utf-8")
    beacon = (root / "scripts" / "beacon.py").read_text(encoding="utf-8")
    assert f'default="{host}"' in agent
    assert f'default="{host}"' in dumb
    assert f'DEFAULT_HOST = "{host}"' in beacon
    bad = 'default="irc.' + 'libera' + '.chat"'
    assert bad not in agent
    assert bad not in dumb


def test_irc_skill_leaflets_exist():
    root = Path(__file__).resolve().parents[1]
    names = (
        "agentic-irc",
        "agentic-moot",
        "agentic-file",
        "agentic-dumb",
        "invite-airc",
        "bob-irc",
    )
    import install_skill as inst

    assert inst.SKILLS == names
    for name in names:
        text = (root / ".grok" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        assert ("name: " + name) in text
    assert "bob-irc" not in inst.COPY_SCRIPTS


def test_install_skill_scripts_include_grok_talk():
    root = Path(__file__).resolve().parents[1]
    import install_skill as inst

    for name in ("grok_talk.py", "grok_talk_drain.py"):
        assert name in inst.SCRIPTS
        assert (root / "scripts" / name).is_file()
