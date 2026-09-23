#!/usr/bin/env python3
"""Discworld guest playtest client.

Plain TCP to the published port. Guest menu G, then the front door in
mud-skill: blank capitalisation, screenreader answer, nothing during the
terms wait, yes at [yes/no], no command until obvious exits, blank line
on the pager, quit waits for "Do come again!".

Does not store or send passwords. Not a full game client.
"""
from __future__ import annotations

import argparse
import random
import re
import select
import socket
import string
import sys
import time

DEFAULT_HOST = "discworld.starturtle.net"
DEFAULT_PORT = 4242
IAC = 255
WILL, WONT, DO, DONT = 251, 252, 253, 254
SB, SE = 250, 240

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07|\x1b.")
# ESC is sometimes already gone, leaving "0;10m" in the map line.
ORPHAN_SGR = re.compile(r"\d+(?:;\d+)+m")
PASSWORD_PROMPT = re.compile(r"(?i)password\s*:")


class LoginError(RuntimeError):
    pass


def strip_ansi(text: str) -> str:
    return ORPHAN_SGR.sub("", ANSI.sub("", text))


def consume_telnet(data: bytes) -> tuple[bytes, bytes, bytes]:
    """Return (clean, replies, unparsed_tail). Refuse WILL/DO. Skip subnegotiation."""
    out = bytearray()
    replies = bytearray()
    i = 0
    while i < len(data):
        if data[i] != IAC:
            out.append(data[i])
            i += 1
            continue
        if i + 1 >= len(data):
            return bytes(out), bytes(replies), data[i:]
        cmd = data[i + 1]
        if cmd == IAC:
            out.append(IAC)
            i += 2
            continue
        if cmd in (WILL, WONT, DO, DONT):
            if i + 2 >= len(data):
                return bytes(out), bytes(replies), data[i:]
            opt = data[i + 2]
            if cmd == WILL:
                replies += bytes([IAC, DONT, opt])
            elif cmd == DO:
                replies += bytes([IAC, WONT, opt])
            i += 3
            continue
        if cmd == SB:
            end = data.find(bytes([IAC, SE]), i + 2)
            if end < 0:
                return bytes(out), bytes(replies), data[i:]
            i = end + 2
            continue
        i += 2
    return bytes(out), bytes(replies), b""


class Conn:
    def __init__(self, sock: socket.socket, log=None):
        self.sock = sock
        self.sock.setblocking(False)
        self.pending = b""
        self.text = ""
        self.closed = False
        self.log = log or (lambda _s: None)

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass

    def pump(self, timeout: float) -> str:
        end = time.time() + timeout
        got = ""
        while time.time() < end:
            wait = min(0.2, end - time.time())
            if wait <= 0:
                break
            readable, _, _ = select.select([self.sock], [], [], wait)
            if not readable:
                continue
            try:
                chunk = self.sock.recv(8192)
            except BlockingIOError:
                continue
            if not chunk:
                self.closed = True
                break
            data = self.pending + chunk
            self.pending = b""
            clean, replies, self.pending = consume_telnet(data)
            if replies:
                try:
                    self.sock.sendall(replies)
                except OSError:
                    self.closed = True
            if not clean:
                continue
            piece = strip_ansi(clean.decode("latin-1", errors="replace")).replace("\r", "")
            self.text += piece
            got += piece
        return got

    def send(self, line: str) -> None:
        self.log(">>> %r\n" % (line,))
        self.sock.sendall((line + "\n").encode("ascii", errors="replace"))

    def wait_for(self, pred, timeout: float, label: str) -> str:
        start = time.time()
        buf = ""
        while time.time() - start < timeout:
            buf += self.pump(min(0.4, timeout - (time.time() - start)))
            if pred(self.text):
                self.log("## WAIT OK %s\n" % label)
                return buf
            if self.closed:
                break
        self.log("## WAIT TIMEOUT %s\n" % label)
        return buf

    def idle_read(self, idle: float, cap: float) -> str:
        start = time.time()
        last = time.time()
        buf = ""
        while time.time() - start < cap:
            chunk = self.pump(0.15)
            if chunk:
                buf += chunk
                last = time.time()
                if "return to continue" in chunk:
                    self.log(">>> '' (pager)\n")
                    self.sock.sendall(b"\n")
                    last = time.time()
                    continue
            elif buf and (time.time() - last) >= idle:
                break
            if self.closed:
                break
        return buf

    def command(self, line: str, idle: float = 1.5, cap: float = 25.0) -> str:
        before = len(self.text)
        self.send(line)
        self.idle_read(idle=idle, cap=cap)
        tail = self.text[before:]
        if "Queued command:" in tail and not tail.strip().endswith(">"):
            self.idle_read(idle=idle, cap=8)
        return self.text[before:]


def connect(host: str, port: int, timeout: float = 20) -> Conn:
    sock = socket.create_connection((host, port), timeout=timeout)
    return Conn(sock)


def guest_login(
    conn: Conn,
    name: str,
    gender: str = "male",
    screenreader: str = "no",
    accept_terms: bool = True,
    menu_timeout: float = 25,
    step_timeout: float = 20,
    terms_timeout: float = 50,
    room_timeout: float = 40,
) -> str:
    """Front door. Sends nothing during the terms wait. Stops on a password prompt."""
    conn.wait_for(lambda t: "Your choice:" in t, menu_timeout, "menu")
    if "Your choice:" not in conn.text:
        raise LoginError("menu not shown")
    conn.send("G")
    conn.wait_for(lambda t: "Enter the name you wish to use:" in t, step_timeout, "name")
    if "Enter the name you wish to use:" not in conn.text:
        raise LoginError("name prompt not shown")
    before_name = len(conn.text)
    conn.send(name)

    def name_ready(t: str) -> bool:
        after_name = t[before_name:]
        return (
            "capitalised" in after_name
            or "banished" in after_name
            or "already trying to create" in after_name
            or PASSWORD_PROMPT.search(after_name) is not None
        )

    conn.wait_for(name_ready, step_timeout, "capitalise")
    after = conn.text[before_name:]
    if PASSWORD_PROMPT.search(after):
        raise LoginError("password prompt; not sending a password")
    if "banished" in after or "already trying to create" in after or "capitalised" not in conn.text:
        raise LoginError("name rejected")
    conn.send("")
    conn.wait_for(lambda t: "male or female" in t, step_timeout, "gender")
    conn.send(gender)
    conn.wait_for(lambda t: "screenreader" in t, step_timeout, "screenreader")
    conn.send(screenreader)
    conn.wait_for(lambda t: "30 seconds" in t, step_timeout, "terms-wait")
    mark = conn.text.rfind("30 seconds")

    def yes_ready(t: str) -> bool:
        return mark >= 0 and "[yes/no]" in t[mark:]

    conn.wait_for(yes_ready, terms_timeout, "yes/no")
    if not yes_ready(conn.text):
        raise LoginError("terms prompt not shown")
    if not accept_terms:
        conn.send("no")
        raise LoginError("terms declined")
    conn.send("yes")
    conn.wait_for(lambda t: "obvious exits" in t, room_timeout, "room")
    if "obvious exits" not in conn.text:
        raise LoginError("room not shown")
    return conn.text


def quit_guest(conn: Conn, timeout: float = 25) -> str:
    conn.send("quit")
    conn.wait_for(lambda t: "Do come again!" in t, timeout, "farewell")
    conn.idle_read(idle=0.4, cap=3)
    if "Do come again!" not in conn.text:
        raise LoginError("quit did not reach Do come again!")
    return conn.text


def default_name() -> str:
    suffix = "".join(random.choice(string.ascii_lowercase) for _ in range(4))
    return "Quill" + suffix


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Discworld guest playtest client")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--name", default="")
    parser.add_argument("--gender", default="male")
    parser.add_argument("--command", action="append", default=[], help="Send after obvious exits. Repeatable.")
    parser.add_argument("--no-quit", action="store_true", help="Do not quit. Leaves a link up.")
    parser.add_argument("--transcript", default="", help="Also write stripped text here.")
    args = parser.parse_args(argv)
    name = args.name or default_name()

    def log(s: str) -> None:
        sys.stdout.write(s)
        sys.stdout.flush()

    log("# guest name=%s host=%s:%s\n" % (name, args.host, args.port))
    conn = connect(args.host, args.port)
    conn.log = log
    code = 0
    try:
        try:
            guest_login(conn, name, gender=args.gender)
        except LoginError as exc:
            log("## LOGIN %s\n" % exc)
            return 2
        for line in args.command:
            if conn.closed:
                break
            conn.command(line)
        if not args.no_quit and not conn.closed:
            try:
                quit_guest(conn)
            except LoginError as exc:
                log("## QUIT %s\n" % exc)
                code = 3
    finally:
        if args.transcript:
            with open(args.transcript, "w", encoding="utf-8") as handle:
                handle.write(conn.text)
        conn.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
