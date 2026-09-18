from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import irc_agent  # noqa: E402
import seal  # noqa: E402


def _args(home: Path, nick: str = "alice") -> argparse.Namespace:
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


def test_433_still_accepts_original_nick(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path / "alice"))
    alice = seal.genkey()
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path / "bob"))
    bob = seal.genkey()
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path / "alice"))
    c = irc_agent.Client(_args(tmp_path / "alice", "alice"))
    c.ident = alice
    c.peers = {"bob": {"pk": bob["pk"], "nick": "bob"}}
    c.live_nick = "alice_l"
    assert c.original_nick == "alice"
    blob = seal.seal_bytes_v2(b"payload", alice["pk"], bob, "#ops", "alice", "bob", "aa11bb22")
    line = seal.irc_lines_v2(blob, "alice", "bob", "aa11bb22")[0]
    c.handle_privmsg("bob!u@h", "#ops", line)
    dest = c.inbox / "aa11bb22.bin"
    assert dest.read_bytes() == b"payload"


def test_wrong_to_nick_not_written(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path / "alice"))
    alice = seal.genkey()
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path / "bob"))
    bob = seal.genkey()
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path / "alice"))
    c = irc_agent.Client(_args(tmp_path / "alice", "alice"))
    c.ident = alice
    c.peers = {"bob": {"pk": bob["pk"], "nick": "bob"}}
    blob = seal.seal_bytes_v2(b"nope", alice["pk"], bob, "#ops", "carol", "bob", "cc00cc00")
    line = seal.irc_lines_v2(blob, "carol", "bob", "cc00cc00")[0]
    c.handle_privmsg("bob!u@h", "#ops", line)
    assert not (c.inbox / "cc00cc00.bin").exists()


def test_replay_clobber_guard_not_crypto(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path / "alice"))
    alice = seal.genkey()
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path / "bob"))
    bob = seal.genkey()
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path / "alice"))
    c = irc_agent.Client(_args(tmp_path / "alice", "alice"))
    c.ident = alice
    c.peers = {"bob": {"pk": bob["pk"], "nick": "bob"}}
    blob = seal.seal_bytes_v2(b"one", alice["pk"], bob, "#ops", "alice", "bob", "r1r1r1r1")
    line = seal.irc_lines_v2(blob, "alice", "bob", "r1r1r1r1")[0]
    c.handle_privmsg("bob!u@h", "#ops", line)
    c.fragments = seal.FragmentStore()
    (c.inbox / "r1r1r1r1.bin").write_bytes(b"one")
    c.handle_privmsg("bob!u@h", "#ops", line)
    assert (c.inbox / "r1r1r1r1.bin").read_bytes() == b"one"


def test_peer_mismatch_does_not_overwrite(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path / "alice"))
    seal.genkey()
    c = irc_agent.Client(_args(tmp_path / "alice", "alice"))
    first = seal.b64(b"\x01" * 32)
    other = seal.b64(b"\x02" * 32)
    c.peers = {"bob": {"pk": first, "nick": "bob"}}
    c.handle_privmsg("bob!u@h", "#ops", "AGPK v1 " + other)
    assert c.peers["bob"]["pk"] == first


def test_sasl_state_machine_waits(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_SASL_USER", "u")
    monkeypatch.setenv("AGENTIC_IRC_SASL_PASSWORD", "p")
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path / "sasl"))
    ns = argparse.Namespace(
        nick="n", channel="#c", home=str(tmp_path / "sasl"), outbox="", hello="",
        announce_key=False, host="h", port=1, realname="r", once=True,
    )
    c = irc_agent.Client(ns)
    out = c.sasl_on_line("CAP", ["ACK"], "sasl")
    assert out == ["AUTHENTICATE PLAIN"]
    assert c.sasl_ack.is_set()
    out = c.sasl_on_line("AUTHENTICATE", [], "+")
    assert out[0].startswith("AUTHENTICATE ") and out[0] != "AUTHENTICATE PLAIN"
    assert c.sasl_plus.is_set()
    out = c.sasl_on_line("903", [], "SASL authentication successful")
    assert out == ["CAP END"]
    assert c.sasl_903.is_set()
    c2 = irc_agent.Client(ns)
    c2.sasl_fail.clear()
    out = c2.sasl_on_line("904", [], "fail")
    assert out == ["CAP END"]
    assert c2.sasl_fail.is_set()


def test_two_homes_isolated(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path / "a"))
    a = seal.genkey()
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path / "b"))
    b = seal.genkey()
    assert a["pk"] != b["pk"]
    assert (tmp_path / "a" / "identity.json").exists()
    assert (tmp_path / "b" / "identity.json").exists()


def test_multi_chunk_forced_small(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path / "a"))
    a = seal.genkey()
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path / "b"))
    b = seal.genkey()
    monkeypatch.setattr(seal, "CHUNK", 8)
    blob = seal.seal_bytes_v2(b"0123456789abcdef", b["pk"], a, "#c", "bob", "alice", "cafecafe")
    lines = seal.irc_lines_v2(blob, "bob", "alice", "cafecafe")
    assert len(lines) > 1
    store = seal.FragmentStore()
    got = None
    for ln in lines:
        got = store.add(seal.parse_seal_line(ln)) or got
    assert got is not None
    pt = seal.open_bytes_v2(seal.b64d(got), b, "#c", "bob", "alice", "cafecafe", a["pk"])
    assert pt == b"0123456789abcdef"


def test_sasl_nak_is_not_ack(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path / "sasl"))
    c = irc_agent.Client(_args(tmp_path / "sasl", "n"))
    assert c.sasl_on_line("CAP", ["NAK"], "sasl") == []
    assert not c.sasl_ack.is_set()


def test_v1_not_written_to_inbox(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path / "alice"))
    alice = seal.genkey()
    c = irc_agent.Client(_args(tmp_path / "alice", "alice"))
    c.ident = alice
    line = "SEAL v1 alice abcdabcd 1 1 QUJDRA=="
    c.handle_privmsg("bob!u@h", "#ops", line)
    assert not list(c.inbox.glob("*.bin"))


def test_wrong_channel_dropped(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path / "alice"))
    alice = seal.genkey()
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path / "bob"))
    bob = seal.genkey()
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path / "alice"))
    c = irc_agent.Client(_args(tmp_path / "alice", "alice"))
    c.ident = alice
    c.peers = {"bob": {"pk": bob["pk"], "nick": "bob"}}
    blob = seal.seal_bytes_v2(b"x", alice["pk"], bob, "#ops", "alice", "bob", "dd11dd11")
    line = seal.irc_lines_v2(blob, "alice", "bob", "dd11dd11")[0]
    c.handle_privmsg("bob!u@h", "#evil", line)
    assert not (c.inbox / "dd11dd11.bin").exists()
