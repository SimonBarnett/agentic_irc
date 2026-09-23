#!/usr/bin/env python3
"""Line-at-a-time Discworld guest session.

Login follows the locked guest path: menu G, name, blank capitalisation,
male, screenreader no, 32 seconds of silence, then yes. After the room
prints an obvious-exits line, commands are read from a file and sent one
at a time. A pager line (return to continue) gets one blank line.

Discworld terms forbid robot scripts. This file is the session client from
the 2026-09-23 guest playtest under the issue #38 exception. It does not
choose fights, buys, or street exits.

No passwords. Guest menu G does not issue one.
"""

import argparse
import os
import re
import socket
import sys
import time

IAC, DONT, DO, WONT, WILL = 255, 254, 253, 252, 251
SB, SE = 250, 240

ANSI = re.compile(
    r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*(?:\x07|\x1b\\)|\x1b."
)


def strip_text(data: bytes) -> str:
    text = data.decode("latin-1", errors="replace")
    text = ANSI.sub("", text)
    text = text.replace("\r", "")
    text = re.sub(r"(?<!\x1b)0;\d+m", "", text)
    return text


class Session:
    def __init__(self, host: str, port: int, out_path: str, raw_path: str):
        self.sock = socket.create_connection((host, port), timeout=20)
        self.sock.settimeout(0.3)
        self.raw = open(raw_path, "wb")
        self.out = open(out_path, "w", encoding="utf-8")
        self.pending = b""
        self.closed = False

    def _write_out(self, text: str) -> None:
        self.out.write(text)
        self.out.flush()
        sys.stdout.write(text)
        sys.stdout.flush()

    def _consume(self, data: bytes) -> str:
        self.raw.write(data)
        self.raw.flush()
        buf = self.pending + data
        self.pending = b""
        text = bytearray()
        i = 0
        replies = bytearray()
        while i < len(buf):
            byte = buf[i]
            if byte != IAC:
                text.append(byte)
                i += 1
                continue
            if i + 1 >= len(buf):
                self.pending = buf[i:]
                break
            cmd = buf[i + 1]
            if cmd == IAC:
                text.append(IAC)
                i += 2
                continue
            if cmd in (WILL, WONT, DO, DONT):
                if i + 2 >= len(buf):
                    self.pending = buf[i:]
                    break
                opt = buf[i + 2]
                if cmd == WILL:
                    replies += bytes([IAC, DONT, opt])
                elif cmd == DO:
                    replies += bytes([IAC, WONT, opt])
                i += 3
                continue
            if cmd == SB:
                end = buf.find(bytes([IAC, SE]), i + 2)
                if end < 0:
                    self.pending = buf[i:]
                    break
                i = end + 2
                continue
            i += 2
        if replies:
            self.sock.sendall(replies)
        return strip_text(bytes(text))

    def read_until(self, seconds: float, stops=None, quiet: float = 1.2) -> str:
        end = time.time() + seconds
        got = ""
        last = time.time()
        while time.time() < end:
            try:
                data = self.sock.recv(65536)
            except socket.timeout:
                if got and (time.time() - last) >= quiet:
                    if not stops or any(s in got for s in stops):
                        break
                    if not stops:
                        break
                continue
            if not data:
                self.closed = True
                got += "\n[[EOF]]\n"
                self._write_out("\n[[EOF]]\n")
                break
            last = time.time()
            piece = self._consume(data)
            if not piece:
                continue
            got += piece
            self._write_out(piece)
            if "return to continue" in piece and "h for help" in got[-400:]:
                time.sleep(0.2)
                self.send_raw("")
                last = time.time()
                continue
            if stops and any(s in got for s in stops) and (time.time() - last) > 0.4:
                self.sock.settimeout(0.3)
                continue
        return got

    def send_raw(self, line: str) -> None:
        payload = (line + "\n").encode("ascii", errors="strict")
        self.sock.sendall(payload)
        self._write_out(f"\n>>> {line!r}\n")

    def send(self, line: str, wait: float = 8, stops=None, quiet: float = 1.4) -> str:
        self.send_raw(line)
        return self.read_until(wait, stops=stops, quiet=quiet)


def login(sess: Session, name: str) -> bool:
    sess._write_out(f"\n=== session {name} ===\n")
    banner = sess.read_until(8, stops=["Your choice:"], quiet=0.8)
    if "Your choice:" not in banner:
        sess._write_out("\n[[no menu]]\n")
        return False
    text = sess.send("G", wait=12, stops=["Enter the name you wish to use:"])
    if "already trying to create" in text or "banished" in text:
        sess._write_out("\n[[name path blocked before name]]\n")
        return False
    text = sess.send(name, wait=12, stops=["capitalised", "already trying", "banished", "Sorry"])
    if "already trying" in text or "banished" in text or (
        "Sorry" in text and "capitalised" not in text
    ):
        sess._write_out("\n[[name rejected]]\n")
        return False
    text = sess.send("", wait=12, stops=["male or female", "screenreader", "terms"])
    if "male or female" in text:
        text = sess.send("male", wait=12, stops=["screenreader", "terms"])
    if "screenreader" in text:
        sess.send("no", wait=8, stops=["30 seconds", "terms"])
    sess._write_out("\n[[waiting 32s for terms]]\n")
    time.sleep(32)
    text = sess.read_until(20, stops=["[yes/no]"], quiet=1.0)
    if "[yes/no]" not in text:
        sess._write_out("\n[[no yes prompt]]\n")
        return False
    text = sess.send("yes", wait=45, stops=["obvious exits"], quiet=2.0)
    if "obvious exits" not in text:
        text += sess.read_until(20, stops=["obvious exits"], quiet=2.0)
    if "obvious exits" not in text:
        sess._write_out("\n[[no room]]\n")
        return False
    sess._write_out("\n[[ROOM READY]]\n")
    return True


def pump(sess: Session, cmd_path: str) -> None:
    offset = 0
    idle_deadline = time.time() + 180
    while time.time() < idle_deadline and not sess.closed:
        if not os.path.exists(cmd_path):
            time.sleep(0.2)
            continue
        with open(cmd_path, "r", encoding="utf-8") as handle:
            handle.seek(offset)
            lines = handle.readlines()
            offset = handle.tell()
        if not lines:
            extra = sess.read_until(0.6, quiet=0.4)
            if extra.strip():
                idle_deadline = time.time() + 180
            continue
        for line in lines:
            cmd = line.rstrip("\n")
            idle_deadline = time.time() + 180
            if cmd == "[[QUITSESSION]]":
                return
            wait = 25 if cmd == "quit" else 12
            got = sess.send(cmd, wait=wait, quiet=1.6)
            if cmd == "quit" and "Do come again!" in got:
                sess.read_until(5, quiet=1.0)
                sess._write_out("\n[[FAREWELL]]\n")
                return
            if "[[EOF]]" in got:
                return
        time.sleep(0.1)
    sess._write_out("\n[[idle timeout]]\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Discworld guest session, one command at a time")
    parser.add_argument("name", help="guest name to type at the name prompt")
    parser.add_argument("--host", default="discworld.starturtle.net")
    parser.add_argument("--port", type=int, default=4242)
    parser.add_argument("--cmds", default="/tmp/dw-cmds")
    parser.add_argument("--out", default="/tmp/dw-out.txt")
    parser.add_argument("--raw", default="/tmp/dw-raw.log")
    args = parser.parse_args()
    open(args.cmds, "w").close()
    sess = Session(args.host, args.port, args.out, args.raw)
    if not login(sess, args.name):
        return
    pump(sess, args.cmds)


if __name__ == "__main__":
    main()
