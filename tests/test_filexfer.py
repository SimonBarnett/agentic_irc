from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import filexfer
import irc_agent
import seal
import wire

FID = "0123456789abcdef"


def _args(home: Path, nick: str = "bob") -> argparse.Namespace:
    return argparse.Namespace(
        nick=nick,
        channel="#ops",
        home=str(home),
        outbox="",
        hello="",
        announce_key=False,
        host="127.0.0.1",
        port=6697,
        realname="test",
        once=True,
    )


def test_filebag_roundtrip():
    bag = filexfer.FileBag()
    data = os.urandom(200)
    b64 = seal.b64(data)
    parts = [b64[i : i + 50] for i in range(0, len(b64), 50)] or [""]
    n = len(parts)
    got = None
    order = list(range(n, 0, -1))  # shuffled reverse
    for i in order:
        got = bag.add_chunk("alice", FID, i, n, parts[i - 1]) or got
    assert got == data


def test_f2_tier_m_20kib_shuffled():
    bag = filexfer.FileBag()
    data = os.urandom(20 * 1024)
    b64 = seal.b64(data)
    parts = [b64[i : i + seal.CHUNK] for i in range(0, len(b64), seal.CHUNK)] or [""]
    n = len(parts)
    assert n <= filexfer.MAX_N_FILE
    got = None
    for i in reversed(range(1, n + 1)):
        got = bag.add_chunk("alice", FID, i, n, parts[i - 1]) or got
    assert got == data
    assert hashlib.sha256(got).hexdigest() == hashlib.sha256(data).hexdigest()


def test_f1_1kib_complete_hash_match(tmp_path):
    data = bytes(range(256)) * 4  # 1024
    sha = hashlib.sha256(data).hexdigest()
    assert filexfer.complete_write(tmp_path, FID, "note.bin", data, sha) is True
    dest = tmp_path / "files" / "complete" / f"{FID}-note.bin"
    assert dest.read_bytes() == data
    assert hashlib.sha256(dest.read_bytes()).hexdigest() == sha
    assert filexfer.complete_write(tmp_path, FID, "note.bin", data, sha) is False


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
    assert wire.parse_file_line(f"FILE v1 OFFER bob alice {FID} 1 aa S foo/bar") is None
    assert wire.parse_file_line(f"FILE v1 OFFER bob alice {FID} 1 aa S foo bar") is None


def test_f6_second_offer_same_id_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    seal.genkey()
    c = irc_agent.Client(_args(tmp_path, "bob"))
    sha = "ab" * 32
    c.handle_privmsg("alice!u@h", "#ops", f"FILE v1 OFFER bob alice {FID} 3 {sha} M note.txt")
    c.handle_privmsg("alice!u@h", "#ops", f"FILE v1 OFFER bob alice {FID} 99 {'cd' * 32} M other.txt")
    offer = c.file_bags._offers[FID]
    assert offer["name"] == "note.txt"
    assert offer["bytes"] == 3


def test_f3_hash_mismatch_done_no_complete(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    seal.genkey()
    c = irc_agent.Client(_args(tmp_path, "bob"))
    data = b"abc"
    bad = "00" * 32
    c.handle_privmsg("alice!u@h", "#ops", f"FILE v1 OFFER bob alice {FID} 3 {bad} M note.txt")
    c.handle_privmsg("alice!u@h", "#ops", f"FILE v1 CHUNK {FID} 1 1 {seal.b64(data)}")
    c.handle_privmsg("alice!u@h", "#ops", f"FILE v1 DONE {FID} {bad}")
    complete = tmp_path / "files" / "complete"
    assert not complete.exists() or not list(complete.glob("*"))


def test_f7_abort_mid_bag(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    seal.genkey()
    c = irc_agent.Client(_args(tmp_path, "bob"))
    data = os.urandom(80)
    b64 = seal.b64(data)
    parts = [b64[:40], b64[40:]]
    sha = hashlib.sha256(data).hexdigest()
    c.handle_privmsg("alice!u@h", "#ops", f"FILE v1 OFFER bob alice {FID} {len(data)} {sha} M note.txt")
    c.handle_privmsg("alice!u@h", "#ops", f"FILE v1 CHUNK {FID} 1 2 {parts[0]}")
    c.handle_privmsg("alice!u@h", "#ops", f"FILE v1 ABORT {FID} :stop")
    c.handle_privmsg("alice!u@h", "#ops", f"FILE v1 CHUNK {FID} 2 2 {parts[1]}")
    c.handle_privmsg("alice!u@h", "#ops", f"FILE v1 DONE {FID} {sha}")
    complete = tmp_path / "files" / "complete"
    assert not complete.exists() or not list(complete.glob("*"))
    assert c.file_bags.take_assembled(FID) is None
    assert not any(k[1] == FID for k in c.file_bags._bags)


def test_f8_disk_cap_refuse_accept(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    monkeypatch.setattr(filexfer, "FILES_HOME_CAP", 10)
    dest = tmp_path / "files" / "complete"
    dest.mkdir(parents=True)
    (dest / "pad.bin").write_bytes(b"0123456789abcdef")
    assert filexfer.would_exceed_cap(tmp_path) is True
    monkeypatch.setattr(sys, "argv", ["filexfer.py", "--home", str(tmp_path), "accept", "--id", FID])
    filexfer.main()
    out = (tmp_path / "outbox.txt").read_text()
    assert f"FILE v1 REFUSE {FID} :disk" in out
    assert "ACCEPT" not in out


def test_f1_done_matching_hash_writes_complete(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    seal.genkey()
    c = irc_agent.Client(_args(tmp_path, "bob"))
    data = bytes(range(256)) * 4
    sha = hashlib.sha256(data).hexdigest()
    b64 = seal.b64(data)
    parts = [b64[i : i + seal.CHUNK] for i in range(0, len(b64), seal.CHUNK)] or [""]
    n = len(parts)
    c.handle_privmsg("alice!u@h", "#ops", f"FILE v1 OFFER bob alice {FID} {len(data)} {sha} M note.bin")
    for i, part in enumerate(parts, 1):
        c.handle_privmsg("alice!u@h", "#ops", f"FILE v1 CHUNK {FID} {i} {n} {part}")
    c.handle_privmsg("alice!u@h", "#ops", f"FILE v1 DONE {FID} {sha}")
    dest = tmp_path / "files" / "complete" / f"{FID}-note.bin"
    assert dest.read_bytes() == data
    assert hashlib.sha256(dest.read_bytes()).hexdigest() == sha
