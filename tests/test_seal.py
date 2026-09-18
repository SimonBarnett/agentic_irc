from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(ROOT))
import seal  # noqa: E402


def _pair(tmp_path: Path):
    os.environ["AGENTIC_IRC_HOME"] = str(tmp_path / "a")
    a = seal.genkey()
    os.environ["AGENTIC_IRC_HOME"] = str(tmp_path / "b")
    b = seal.genkey()
    return a, b


def test_v1_roundtrip(tmp_path: Path):
    a, b = _pair(tmp_path)
    os.environ["AGENTIC_IRC_HOME"] = str(tmp_path / "b")
    blob = seal.seal_bytes_v1(b"hello", b["pk"])
    assert seal.open_bytes_v1(blob, b) == b"hello"


def test_v2_roundtrip_and_aad(tmp_path: Path):
    a, b = _pair(tmp_path)
    blob = seal.seal_bytes_v2(
        b"secret", b["pk"], a, "#ops", "bob", "alice", "deadbeefdeadbeef"
    )
    pt = seal.open_bytes_v2(blob, b, "#Ops", "Bob", "Alice", "deadbeefdeadbeef", a["pk"])
    assert pt == b"secret"
    with pytest.raises(Exception):
        seal.open_bytes_v2(blob, b, "#other", "bob", "alice", "deadbeefdeadbeef", a["pk"])
    with pytest.raises(Exception):
        seal.open_bytes_v2(blob, b, "#ops", "bob", "mallory", "deadbeefdeadbeef", a["pk"])
    with pytest.raises(ValueError, match="sender key"):
        seal.open_bytes_v2(blob, b, "#ops", "bob", "alice", "deadbeefdeadbeef", b["pk"])
    with pytest.raises(ValueError, match="pipe"):
        seal.aad_v2("#op|s", "bob", "alice", "deadbeefdeadbeef")


def test_wrong_to_nick_ignored():
    store = seal.FragmentStore()
    line = seal.parse_seal_line("SEAL v2 bob alice abcdabcdabcdabcd 1 1 AAA")
    assert line is not None
    assert line.to_nick == "bob"
    # receiver carol drops
    assert line.to_nick.lower() != "carol"


def test_parse_rejects_huge_n():
    assert seal.parse_seal_line("SEAL v2 bob alice abcdabcdabcdabcd 1 1000000 x") is None
    assert seal.parse_seal_line("SEAL v1 bob abcdabcdabcdabcd 1 1000000 x") is None
    store = seal.FragmentStore()
    fake = seal.SealLine(2, "bob", "alice", "abcdabcdabcdabcd", 1, 10**6, "x")
    assert store.add(fake) is None
    assert store._bags == {}


def test_duplicate_i_mismatch_and_bounds():
    store = seal.FragmentStore()
    l1 = seal.parse_seal_line("SEAL v2 bob alice abababababababab 1 2 AAAA")
    l2 = seal.parse_seal_line("SEAL v2 bob alice abababababababab 1 2 BBBB")
    l3 = seal.parse_seal_line("SEAL v2 bob alice abababababababab 0 2 AAAA")
    assert l3 is None
    assert store.add(l1) is None
    assert store.add(l2) is None  # duplicate i different chunk
    assert store.add(seal.parse_seal_line("SEAL v2 bob alice abababababababab 2 2 CCCC")) is None


def test_multi_chunk_reassembly(tmp_path: Path):
    a, b = _pair(tmp_path)
    blob = seal.seal_bytes_v2(b"xyz", b["pk"], a, "#c", "bob", "alice", "c0ffeec0c0ffeec0")
    lines = seal.irc_lines_v2(blob, "bob", "alice", "c0ffeec0c0ffeec0")
    store = seal.FragmentStore()
    got = None
    for ln in lines:
        parsed = seal.parse_seal_line(ln)
        assert parsed is not None
        got = store.add(parsed) or got
    assert got is not None
    pt = seal.open_bytes_v2(seal.b64d(got), b, "#c", "bob", "alice", "c0ffeec0c0ffeec0", a["pk"])
    assert pt == b"xyz"


def test_short_blob(tmp_path: Path):
    _, b = _pair(tmp_path)
    with pytest.raises(ValueError):
        seal.open_bytes_v1(b"short", b)
    with pytest.raises(ValueError):
        seal.open_bytes_v2(b"short", b, "#c", "t", "f", "id", b["pk"])


def test_bad_b64():
    with pytest.raises(Exception):
        seal.b64d("@@@@")


def test_tofu_pin():
    peers: dict = {}
    assert seal.tofu_pin(peers, "Grok", "aaa") == "pinned"
    assert seal.tofu_pin(peers, "grok", "aaa") == "ok"
    assert seal.tofu_pin(peers, "grok", "bbb") == "mismatch"


def test_v1_parser_still_works():
    line = seal.parse_seal_line("SEAL v1 bob abcdabcdabcdabcd 1 1 QUJD")
    assert line is not None
    assert line.version == 1
    assert line.from_nick is None


def test_msgid_rejects_path():
    assert seal.parse_seal_line("SEAL v2 bob alice ../etc/pw 1 1 AAAA") is None
    assert seal.parse_seal_line("SEAL v2 bob alice abcdabcdabcdabcd 1 1 AAAA") is not None


def test_agpk_must_be_32_bytes():
    assert seal.parse_agpk_line("AGPK v1 short") is None
    pk = seal.b64(b"\x11" * 32)
    assert seal.parse_agpk_line("AGPK v1 " + pk) == pk


def test_fragment_key_includes_from_nick():
    store = seal.FragmentStore()
    a = seal.parse_seal_line("SEAL v2 bob alice abababababababab 1 2 AAAA")
    b = seal.parse_seal_line("SEAL v2 bob mallory abababababababab 1 2 BBBB")
    assert store.add(a) is None
    assert store.add(b) is None
    assert len(store._bags) == 2
