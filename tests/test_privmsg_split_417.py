"""FR #205: split long PRIVMSG; log 417; never split UTF-8 codepoints."""
from __future__ import annotations

import io
from pathlib import Path
from unittest import mock

import irc_agent


def test_short_privmsg_unchanged():
    line = "PRIVMSG #marchhare :hello short"
    assert irc_agent.expand_irc_outbound_line(line, nick="bob-marchhare", text_max=400) == [line]


def test_600_char_addressed_split_reassembles_and_keeps_prefix():
    body = "marchhare-34992: " + ("word " * 120)  # well over 600 chars
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
    # snowman is 3 bytes; force tiny budget so we split often
    snow = "\u2603"
    text = snow * 50
    pieces = irc_agent.split_utf8_by_words(text, max_bytes=8)
    assert "".join(pieces) == text
    for p in pieces:
        # each piece must be valid utf-8 roundtrip and not end mid-codepoint
        assert p.encode("utf-8").decode("utf-8") == p
        assert len(p.encode("utf-8")) <= 8 or len(p) == 1


def test_417_logs_info_preview_not_full_body(tmp_path, monkeypatch, capsys):
    args = mock.Mock(
        host="127.0.0.1",
        port=6697,
        nick="bob-marchhare",
        channel="#marchhare",
        home=str(tmp_path),
        outbox="",
        hello="",
        password="",
        chair=False,
    )
    # minimal Client without connect
    c = irc_agent.Client.__new__(irc_agent.Client)
    c.args = args
    c.home = tmp_path
    c.original_nick = "bob-marchhare"
    c.live_nick = "bob-marchhare"
    c.debug = False
    c.stop = mock.Mock()
    c.stop.is_set.return_value = False
    c.ready = mock.Mock()
    c.ready.is_set.return_value = True
    c.joined = mock.Mock()
    c.dead = mock.Mock()
    c.sock = mock.Mock()
    c.lock = __import__("threading").Lock()
    c._linelen = 512
    c.channels = ["#marchhare"]
    c._pending_joins = set()
    c.sasl_on_line = lambda *a, **k: []
    c.handle_privmsg = lambda *a, **k: None
    c.handle_join = lambda *a, **k: None
    c.handle_part = lambda *a, **k: None
    c.handle_quit = lambda *a, **k: None
    c._last_server_rx = 0.0
    c._pong_due_at = 0.0

    long_secret = "SECRETTOKEN_" + ("x" * 200)
    # feed one 417 line then close
    payload = f":irc.ntsa.uk 417 bob-marchhare :Line too long {long_secret}\r\n".encode()
    c.sock.recv = mock.Mock(side_effect=[payload, b""])

    c.reader()
    out = capsys.readouterr().out
    assert "INFO 417 line too long" in out
    assert "nick=bob-marchhare" in out
    assert "preview=" in out
    assert long_secret not in out
    assert "SECRETTOKEN_" not in out or out.count("SECRETTOKEN_") == 0


def test_drain_outbox_splits_long_privmsg(tmp_path, monkeypatch):
    home = tmp_path
    args = mock.Mock(
        host="h",
        port=1,
        nick="bob-marchhare",
        channel="#marchhare",
        home=str(home),
        outbox="",
        hello="",
        password="",
        chair=False,
    )
    # build via real constructor if easy — use __new__ + fields like other tests
    import test_agent as ta  # may not export helper

    sent: list[str] = []

    class C(irc_agent.Client):
        def send(self, line: str) -> None:
            sent.append(line)

    # use Client factory pattern from test_agent
    from argparse import Namespace

    a = Namespace(
        host="127.0.0.1",
        port=6697,
        nick="bob-marchhare",
        channel="#marchhare,#bobiverse",
        home=str(home),
        outbox="",
        hello="",
        password="",
        chair=False,
        announce_key="",
        listen="",
    )
    # Client.__init__ needs many things - monkeypatch connect
    monkeypatch.setattr(irc_agent.Client, "connect", lambda self: mock.Mock())
    c = irc_agent.Client(a)
    c.sock = mock.Mock()
    c.joined.set()
    c.send = lambda line: sent.append(line)  # type: ignore
    c.live_nick = "bob-marchhare"
    c._privmsg_text_max = 80
    body = "marchhare-34992: " + ("assign work " * 40)
    (home / "outbox.txt").write_text(f"PRIVMSG #marchhare :{body}\n", encoding="utf-8")
    drained = c.drain_outbox_once()
    assert len(drained) >= 2
    assert all(x.startswith("PRIVMSG #marchhare :marchhare-34992: ") for x in drained)
    texts = [x.split(" :", 1)[1] for x in drained]
    assert irc_agent.reassemble_privmsg_bodies(texts) == body
