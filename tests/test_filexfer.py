from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import filexfer
import seal
import wire


def test_filebag_roundtrip():
    bag = filexfer.FileBag()
    data = os.urandom(200)
    b64 = seal.b64(data)
    parts = [b64[i : i + 50] for i in range(0, len(b64), 50)] or [""]
    n = len(parts)
    got = None
    order = list(range(n, 0, -1))  # shuffled reverse
    for i in order:
        got = bag.add_chunk("alice", "0123456789abcdef", i, n, parts[i - 1]) or got
    assert got == data


def test_hash_mismatch_complete_write(tmp_path):
    ok = filexfer.complete_write(tmp_path, "0123456789abcdef", "x.txt", b"abc", "00" * 32)
    assert ok is False
    assert not list((tmp_path / "files" / "complete").glob("*")) if (tmp_path / "files" / "complete").exists() else True


def test_offer_identity_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    ident = tmp_path / "identity.json"
    ident.write_text("{}")
    ns = type("A", (), {})()
    ns.home = str(tmp_path)
    ns.infile = str(ident)
    ns.to = "bob"
    ns.from_nick = "alice"
    ns.tier = "M"
    ns.channel = "#ops"
    try:
        filexfer.offer(ns)
        assert False, "should refuse"
    except SystemExit:
        pass


def test_pathlike_name_rejected():
    mid = "0123456789abcdef"
    assert wire.parse_file_line(f"FILE v1 OFFER bob alice {mid} 1 aa S foo/bar") is None
    assert wire.parse_file_line(f"FILE v1 OFFER bob alice {mid} 1 aa S foo bar") is None
