"""Channel ping -> immediate pong from bob-* and named agents (no Grok enqueue)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bobstat
import grok_talk
import irc_agent


def _args(home: Path, nick: str = "bob-ionos", channel: str = "#bobiverse") -> argparse.Namespace:
    return argparse.Namespace(
        nick=nick,
        channel=channel,
        home=str(home),
        outbox="",
        hello="",
        announce_key=False,
        host="127.0.0.1",
        port=6697,
        realname="test",
        once=True,
        password="",
    )


def _client(tmp_path: Path, monkeypatch, nick: str = "bob-ionos") -> tuple[irc_agent.Client, list[str]]:
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    sent: list[str] = []

    def _send(self, line: str) -> None:
        sent.append(line)

    monkeypatch.setattr(irc_agent.Client, "send", _send)
    monkeypatch.setattr(irc_agent.time, "sleep", lambda *_a, **_k: None)
    c = irc_agent.Client(_args(tmp_path, nick=nick))
    return c, sent


def test_bare_ping_on_bobiverse_pongs(tmp_path, monkeypatch):
    c, sent = _client(tmp_path, monkeypatch)
    c.handle_privmsg("simon!u@h", "#bobiverse", "ping")
    assert sent == ["PRIVMSG #bobiverse :pong"]


def test_ping_case_and_trim(tmp_path, monkeypatch):
    c, sent = _client(tmp_path, monkeypatch)
    c.handle_privmsg("simon!u@h", "#bobiverse", "  PING  ")
    assert sent == ["PRIVMSG #bobiverse :pong"]


def test_ping_on_shop_channel_replies_there(tmp_path, monkeypatch):
    c, sent = _client(tmp_path, monkeypatch, nick="bob-ionos")
    assert "#ionos" in [ch.lower() for ch in c.channels]
    c.handle_privmsg("simon!u@h", "#ionos", "Ping")
    assert sent == ["PRIVMSG #ionos :pong"]


def test_non_bare_ping_does_not_pong(tmp_path, monkeypatch):
    c, sent = _client(tmp_path, monkeypatch)
    c.handle_privmsg("simon!u@h", "#bobiverse", "ping please")
    c.handle_privmsg("simon!u@h", "#bobiverse", "ping!")
    assert sent == []


def test_talk_seat_does_not_auto_pong(tmp_path, monkeypatch):
    c, sent = _client(tmp_path, monkeypatch, nick="ionos-17568")
    c.handle_privmsg("simon!u@h", "#bobiverse", "ping")
    assert sent == []


def test_query_ping_is_not_channel_pong(tmp_path, monkeypatch):
    """PM 'ping' stays on the mention path. Channel auto-pong does not fire."""
    c, sent = _client(tmp_path, monkeypatch)
    c.handle_privmsg("simon!u@h", "bob-ionos", "ping")
    assert not any(line.split(" :", 1)[-1] == "pong" for line in sent)


def test_unjoined_channel_ignored(tmp_path, monkeypatch):
    c, sent = _client(tmp_path, monkeypatch)
    c.handle_privmsg("simon!u@h", "#not-joined", "ping")
    assert sent == []


def test_ping_does_not_enqueue_grok(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_GROK_TALK", "1")
    bobstat.write_peer(
        tmp_path,
        {"ok": True, "id": "ionos", "weekly": 12, "running": 0, "queued": 0, "jobs": []},
    )
    c, sent = _client(tmp_path, monkeypatch)
    c.handle_privmsg("simon!u@h", "#bobiverse", "ping")
    assert sent == ["PRIVMSG #bobiverse :pong"]
    assert not grok_talk.inbox_path(tmp_path).exists()


def test_named_agent_bare_ping_pongs(tmp_path, monkeypatch):
    c, sent = _client(tmp_path, monkeypatch, nick="Haitch")
    c.handle_privmsg("simon!u@h", "#bobiverse", "ping")
    assert sent == ["PRIVMSG #bobiverse :pong"]


def test_named_agent_directed_full_nick(tmp_path, monkeypatch):
    c, sent = _client(tmp_path, monkeypatch, nick="Haitch")
    c.handle_privmsg("simon!u@h", "#bobiverse", "ping haitch")
    assert sent == ["PRIVMSG #bobiverse :pong"]


def test_named_agent_ping_colon_nick(tmp_path, monkeypatch):
    c, sent = _client(tmp_path, monkeypatch, nick="Haitch")
    c.handle_privmsg("simon!u@h", "#bobiverse", "ping: Haitch")
    assert sent == ["PRIVMSG #bobiverse :pong"]


def test_directed_ping_wrong_nick_silent(tmp_path, monkeypatch):
    c, sent = _client(tmp_path, monkeypatch, nick="Haitch")
    c.handle_privmsg("simon!u@h", "#bobiverse", "ping jeeves")
    assert sent == []


def test_partial_prefix_matches_bob(tmp_path, monkeypatch):
    c, sent = _client(tmp_path, monkeypatch, nick="bob-ionos")
    c.handle_privmsg("simon!u@h", "#bobiverse", "ping bob")
    assert sent == ["PRIVMSG #bobiverse :pong"]


def test_partial_substring_haitch(tmp_path, monkeypatch):
    c, sent = _client(tmp_path, monkeypatch, nick="Haitch")
    c.handle_privmsg("simon!u@h", "#bobiverse", "ping ait")
    assert sent == ["PRIVMSG #bobiverse :pong"]


def test_short_substring_too_ambiguous(tmp_path, monkeypatch):
    """Selectors shorter than 3 chars only match exact or prefix, not mid-string."""
    c, sent = _client(tmp_path, monkeypatch, nick="Haitch")
    c.handle_privmsg("simon!u@h", "#bobiverse", "ping ai")
    assert sent == []


def test_wildcard_bob_star(tmp_path, monkeypatch):
    c, sent = _client(tmp_path, monkeypatch, nick="bob-marchhare")
    c.handle_privmsg("simon!u@h", "#bobiverse", "ping bob-*")
    assert sent == ["PRIVMSG #bobiverse :pong"]


def test_wildcard_bob_star_named_silent(tmp_path, monkeypatch):
    c, sent = _client(tmp_path, monkeypatch, nick="Haitch")
    c.handle_privmsg("simon!u@h", "#bobiverse", "ping bob-*")
    assert sent == []


def test_wildcard_question_mark(tmp_path, monkeypatch):
    c, sent = _client(tmp_path, monkeypatch, nick="Haitch")
    c.handle_privmsg("simon!u@h", "#bobiverse", "ping Haitc?")
    assert sent == ["PRIVMSG #bobiverse :pong"]


def test_nick_match_helper_unit():
    m = irc_agent.Client._nick_matches_ping_selector
    assert m("bob-ionos", "bob-ionos")
    assert m("bob-ionos", "bob")
    assert m("bob-ionos", "bob-*")
    assert m("bob-ionos", "*-ionos")
    assert m("Haitch", "hait")
    assert m("Haitch", "ait")
    assert not m("Haitch", "ai")  # too short for substring
    assert not m("Haitch", "bob-*")
    assert not m("Haitch", "jeeves")
