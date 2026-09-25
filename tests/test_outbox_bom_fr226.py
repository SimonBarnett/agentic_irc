"""FR #226: outbox BOM + pre-wrapped PRIVMSG must not double-wrap."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import irc_agent
import shop_listen


def _wire_bodies(sent: list[str]) -> list[str]:
    out = []
    for s in sent:
        if s.upper().startswith("PRIVMSG "):
            rest = s[8:]
            if " :" in rest:
                _t, _, body = rest.partition(" :")
                out.append(body)
            else:
                out.append(s)
        else:
            out.append(s)
    return out


def test_normalize_bom_prewrapped_and_clean():
    nick = "marchhare-34992"
    ack = f"{nick} ACK FR SimonBarnett/agentic_irc#226"
    clean = ack
    bom = "\ufeff" + f"PRIVMSG #marchhare :{ack}"
    pre = f"PRIVMSG #marchhare :{ack}"
    double = f"PRIVMSG #marchhare :PRIVMSG #marchhare :{ack}"

    k0, n0 = irc_agent.normalize_outbox_line(clean)
    assert k0 == "bare" and n0 == ack

    k1, n1 = irc_agent.normalize_outbox_line(bom)
    assert k1 == "privmsg"
    assert n1 == f"PRIVMSG #marchhare :{ack}"
    assert "\ufeff" not in n1
    assert n1.count("PRIVMSG") == 1

    k2, n2 = irc_agent.normalize_outbox_line(pre)
    assert k2 == "privmsg" and n2 == f"PRIVMSG #marchhare :{ack}"

    k3, n3 = irc_agent.normalize_outbox_line(double)
    assert k3 == "privmsg"
    assert n3 == f"PRIVMSG #marchhare :{ack}"
    assert n3.count("PRIVMSG") == 1


def test_take_outbox_lines_file_bom_and_line_bom(tmp_path: Path):
    nick = "marchhare-34992"
    ack = f"{nick} ACK FR SimonBarnett/x#1"
    path = tmp_path / "outbox.txt"
    # UTF-8 BOM + pre-wrapped line; second line bare clean
    raw = (
        b"\xef\xbb\xbf"
        + f"PRIVMSG #marchhare :{ack}\n".encode("utf-8")
        + f"{nick} DONE FR SimonBarnett/x#1 ok https://example.test/p/1\n".encode("utf-8")
        + b"\xef\xbb\xbfPRIVMSG #marchhare :"
        + f"{nick} ACK FR SimonBarnett/x#2\n".encode("utf-8")
    )
    path.write_bytes(raw)
    lines, _pos = irc_agent.take_outbox_lines(path, 0)
    assert len(lines) == 3
    assert lines[0] == f"PRIVMSG #marchhare :{ack}"
    assert lines[0].count("PRIVMSG") == 1
    assert "\ufeff" not in lines[0]
    assert lines[1] == f"{nick} DONE FR SimonBarnett/x#1 ok https://example.test/p/1"
    assert lines[2] == f"PRIVMSG #marchhare :{nick} ACK FR SimonBarnett/x#2"
    assert lines[2].count("PRIVMSG") == 1


def test_drain_sends_single_privmsg(tmp_path: Path):
    home = tmp_path / "h"
    home.mkdir()
    outbox = home / "outbox.txt"
    nick = "marchhare-34992"
    ack = f"{nick} ACK FR SimonBarnett/agentic_irc#226"
    # BOM + pre-wrapped — the MarchHare failure mode
    outbox.write_bytes(b"\xef\xbb\xbf" + f"PRIVMSG #marchhare :{ack}\n".encode("utf-8"))

    args = argparse.Namespace(
        nick=nick,
        channel="#marchhare,#bobiverse",
        home=str(home),
        outbox=str(outbox),
        hello="",
        announce_key=False,
        host="127.0.0.1",
        port=6697,
        realname="t",
        once=True,
        password="",
        chair=False,
    )
    client = irc_agent.Client(args)
    client.channels = ["#marchhare", "#bobiverse"]
    client.live_nick = nick
    client.joined.set()
    client.sock = object()  # pretend connected
    sent: list[str] = []

    def capture(line: str) -> None:
        sent.append(line)

    client.send = capture  # type: ignore[method-assign]

    client.drain_outbox_once()
    assert sent, "expected wire send"
    # exactly one PRIVMSG layer
    for s in sent:
        assert s.upper().startswith("PRIVMSG ")
        assert s.count("PRIVMSG") == 1
        assert "\ufeff" not in s
    bodies = _wire_bodies(sent)
    assert any(ack in b for b in bodies)
    # must not be PRIVMSG #chan :PRIVMSG ...
    assert not any(b.upper().startswith("PRIVMSG ") for b in bodies)


def test_write_outbox_line_no_bom(tmp_path: Path):
    path = tmp_path / "outbox.txt"
    irc_agent.write_outbox_line(path, "flamingo-1 ACK FR o/r#1")
    data = path.read_bytes()
    assert not data.startswith(b"\xef\xbb\xbf")
    assert data.decode("utf-8") == "flamingo-1 ACK FR o/r#1\n"
    irc_agent.write_outbox_line(path, "DONE FR o/r#1 ok", channel="#flamingo")
    text = path.read_text(encoding="utf-8")
    assert "PRIVMSG #flamingo :DONE FR o/r#1 ok\n" in text


def test_shop_listen_parses_bom_and_prewrapped():
    nick = "marchhare-34992"
    body = f"{nick} ACK FR SimonBarnett/agentic_irc#226"
    cases = [
        body,
        "\ufeff" + body,
        f"PRIVMSG #marchhare :{body}",
        f"\ufeffPRIVMSG #marchhare :{body}",
        f"PRIVMSG #marchhare :PRIVMSG #marchhare :{body}",
    ]
    for c in cases:
        p = shop_listen.parse_shop_job_line(c)
        assert p is not None, repr(c)
        assert p.verb == "ACK"
        assert p.repo == "SimonBarnett/agentic_irc"
        assert p.id == "#226"
