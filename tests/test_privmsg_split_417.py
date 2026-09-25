"""FR #205: split long PRIVMSG; log 417; never split UTF-8 codepoints."""
from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import irc_agent  # noqa: E402


def _args(home: Path, nick: str = "bob-marchhare") -> argparse.Namespace:
    return argparse.Namespace(
        nick=nick,
        channel="#marchhare",
        home=str(home),
        outbox="",
        hello="",
        announce_key=False,
        host="127.0.0.1",
        port=6697,
        realname="test",
        once=True,
        password="",
        chair=False,
    )


def test_short_privmsg_unchanged():
    line = "PRIVMSG #marchhare :hello short"
    assert irc_agent.expand_irc_outbound_line(line, nick="bob-marchhare", text_max=400) == [line]


def test_600_char_addressed_split_reassembles_and_keeps_prefix():
    body = "marchhare-34992: " + ("word " * 120)
    assert len(body) >= 600
    line = f"PRIVMSG #marchhare :{body}"
    wires = irc_agent.expand_irc_outbound_line(line, nick="bob-marchhare", text_max=200)
    assert len(wires) >= 2
    texts = []
    for w in wires:
        assert w.startswith("PRIVMSG #marchhare :")
        t = w.split(" :", 1)[1]
        assert t.startswith("marchhare-34992: ")
        assert len(t.encode("utf-8")) <= 200
        texts.append(t)
    assert irc_agent.reassemble_privmsg_bodies(texts) == body


def test_multibyte_utf8_never_split_across_pieces():
    snow = "\u2603"  # 3-byte UTF-8
    text = snow * 50
    pieces = irc_agent.split_utf8_by_words(text, max_bytes=8)
    assert "".join(pieces) == text
    for p in pieces:
        assert p.encode("utf-8").decode("utf-8") == p
        assert all(len(ch.encode("utf-8")) <= 8 for ch in p)
        assert len(p.encode("utf-8")) <= 8


def test_417_logs_info_preview_not_full_body(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    c = irc_agent.Client(_args(tmp_path))
    c.sock = mock.Mock()
    c.lock = threading.Lock()
    c.stop = threading.Event()
    c.ready = threading.Event()
    c.ready.set()
    c.joined = threading.Event()
    c.dead = threading.Event()
    c.debug = None  # no irc.log path
    c.live_nick = "bob-marchhare"
    c.channels = ["#marchhare"]
    c._pending_joins = set()
    c.sasl_on_line = lambda *a, **k: []  # type: ignore
    c.handle_privmsg = lambda *a, **k: None  # type: ignore
    long_secret = "SECRETTOKEN_" + ("x" * 200)
    payload = f":irc.ntsa.uk 417 bob-marchhare :Line too long {long_secret}\r\n".encode()
    c.sock.recv = mock.Mock(side_effect=[payload, b""])
    c.reader()
    out = capsys.readouterr().out
    assert "INFO 417 line too long" in out
    assert "nick=bob-marchhare" in out
    assert "preview=" in out
    assert long_secret not in out
    assert "SECRETTOKEN_" not in out


def test_drain_outbox_splits_long_privmsg(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    c = irc_agent.Client(_args(tmp_path))
    c.sock = mock.Mock()
    c.joined.set()
    c.live_nick = "bob-marchhare"
    c._privmsg_text_max = 80
    sent: list[str] = []
    c.send = lambda line: sent.append(line)  # type: ignore
    body = "marchhare-34992: " + ("assign work " * 40)
    (tmp_path / "outbox.txt").write_text(f"PRIVMSG #marchhare :{body}\n", encoding="utf-8")
    drained = c.drain_outbox_once()
    assert len(drained) >= 2
    assert all(x.startswith("PRIVMSG #marchhare :marchhare-34992: ") for x in drained)
    texts = [x.split(" :", 1)[1] for x in drained]
    assert irc_agent.reassemble_privmsg_bodies(texts) == body
    assert sent == drained
