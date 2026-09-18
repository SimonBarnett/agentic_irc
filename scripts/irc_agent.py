#!/usr/bin/env python3
"""TLS IRC agent: outbox → channel, AGPK announce, SEAL reassembly into inbox.

Lessons from WIN-MPRE8VI4U6U / grok-ionos-ntsa:
- wrap_socket then settimeout(None); create_connection timeout must not stay on the socket
- PING/PONG on the reader thread
- write outbound lines to an outbox file; do not block the agent on the socket
- never PRIVMSG secrets; SEAL lines only
"""
from __future__ import annotations

import argparse
import os
import socket
import ssl
import sys
import threading
import time
from collections import defaultdict
from pathlib import Path

# allow `python scripts/irc_agent.py` without installing a package
sys.path.insert(0, str(Path(__file__).resolve().parent))
import seal  # noqa: E402


def send(sock: ssl.SSLSocket, lock: threading.Lock, line: str) -> None:
    with lock:
        sock.sendall((line + "\r\n").encode("utf-8"))


def say(sock: ssl.SSLSocket, lock: threading.Lock, chan: str, msg: str) -> None:
    send(sock, lock, "PRIVMSG " + chan + " :" + msg)


def reader(
    sock: ssl.SSLSocket,
    lock: threading.Lock,
    nick: str,
    chan: str,
    ready: threading.Event,
    joined: threading.Event,
    seals: dict,
    inbox: Path,
    ident: dict | None,
) -> None:
    buf = b""
    while True:
        data = sock.recv(4096)
        if not data:
            print("DISCONNECTED", flush=True)
            os._exit(1)
        buf += data
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            t = line.decode("utf-8", "replace").rstrip("\r")
            print(t, flush=True)
            if t.startswith("PING "):
                send(sock, lock, "PONG " + t[5:])
                continue
            parts = t.split(" ")
            if len(parts) >= 2 and parts[1] == "001":
                ready.set()
            if len(parts) >= 3 and parts[1] == "JOIN" and chan.lower() in t.lower():
                joined.set()
            if len(parts) >= 2 and parts[1] in ("433", "432"):
                send(sock, lock, "NICK " + nick + "_l")
            # trailing PRIVMSG text
            if len(parts) >= 4 and parts[1] == "PRIVMSG":
                body = t.split(" :", 1)[-1] if " :" in t else ""
                handle_body(body, nick, seals, inbox, ident)


def handle_body(body: str, nick: str, seals: dict, inbox: Path, ident: dict | None) -> None:
    if body.startswith("AGPK v1 "):
        return
    parsed = seal.parse_seal_line(body)
    if not parsed:
        return
    to_nick, msg_id, i, n, chunk = parsed
    if to_nick.lower() not in (nick.lower(), nick.lower() + "_l", "*"):
        return
    bag = seals[msg_id]
    bag[i] = chunk
    bag["_n"] = n
    if len([k for k in bag if isinstance(k, int)]) < n:
        return
    b64 = "".join(bag[j] for j in range(1, n + 1))
    seals.pop(msg_id, None)
    if ident is None:
        print(f"SEAL {msg_id} complete but no identity; not decrypting", flush=True)
        return
    try:
        pt = seal.open_bytes(seal.b64d(b64), ident)
    except Exception as e:
        print(f"SEAL {msg_id} decrypt failed: {type(e).__name__}", flush=True)
        return
    inbox.mkdir(parents=True, exist_ok=True)
    dest = inbox / f"{msg_id}.bin"
    dest.write_bytes(pt)
    try:
        os.chmod(dest, 0o600)
    except OSError:
        pass
    print(f"SEAL {msg_id} -> {dest} ({len(pt)} bytes)", flush=True)


def outbox_loop(sock: ssl.SSLSocket, lock: threading.Lock, chan: str, path: Path, joined: threading.Event) -> None:
    joined.wait()
    last = 0
    if path.exists():
        last = path.stat().st_size
    while True:
        time.sleep(1)
        if not path.exists():
            continue
        sz = path.stat().st_size
        if sz < last:
            last = 0
        if sz <= last:
            continue
        with path.open("r", encoding="utf-8", errors="replace") as f:
            f.seek(last)
            chunk = f.read()
            last = f.tell()
        for line in chunk.splitlines():
            line = line.strip()
            if line:
                say(sock, lock, chan, line)


def main() -> None:
    p = argparse.ArgumentParser(description="agentic TLS IRC")
    p.add_argument("--host", default="irc.libera.chat")
    p.add_argument("--port", type=int, default=6697)
    p.add_argument("--nick", required=True)
    p.add_argument("--channel", required=True)
    p.add_argument("--realname", default="agentic-irc")
    p.add_argument("--outbox", default="", help="append-only file of PRIVMSG lines")
    p.add_argument("--hello", default="", help="one public line after JOIN (no secrets)")
    p.add_argument("--announce-key", action="store_true", help="PRIVMSG AGPK v1 after JOIN")
    args = p.parse_args()
    chan = args.channel if args.channel.startswith("#") else "#" + args.channel
    irc_home = seal.home()
    outbox = Path(args.outbox) if args.outbox else irc_home / "outbox.txt"
    inbox = irc_home / "inbox"
    ident = None
    if seal.ident_path().exists():
        ident = seal.load_ident()

    ctx = ssl.create_default_context()
    raw = socket.create_connection((args.host, args.port), 20)
    raw.settimeout(None)
    sock = ctx.wrap_socket(raw, server_hostname=args.host)
    sock.settimeout(None)

    lock = threading.Lock()
    ready = threading.Event()
    joined = threading.Event()
    seals: dict = defaultdict(dict)

    threading.Thread(
        target=reader,
        args=(sock, lock, args.nick, chan, ready, joined, seals, inbox, ident),
        daemon=True,
    ).start()
    threading.Thread(target=outbox_loop, args=(sock, lock, chan, outbox, joined), daemon=True).start()

    send(sock, lock, "NICK " + args.nick)
    send(sock, lock, f"USER {args.nick} 0 * :{args.realname}")
    if not ready.wait(30):
        print("NO 001", flush=True)
        os._exit(2)
    time.sleep(1)
    send(sock, lock, "JOIN " + chan)
    if not joined.wait(30):
        print("NO JOIN", flush=True)
        os._exit(3)
    time.sleep(1)
    if args.hello:
        say(sock, lock, chan, args.hello)
    if args.announce_key:
        if ident is None:
            print("no identity; skip AGPK", flush=True)
        else:
            say(sock, lock, chan, "AGPK v1 " + ident["pk"])
    print(f"joined {chan} as {args.nick}; outbox={outbox}", flush=True)
    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()
