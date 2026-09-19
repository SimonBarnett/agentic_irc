#!/usr/bin/env python3
"""TLS IRC agent: reconnect, SASL from env, flood delay, AGPK TOFU, SEAL v2 inbox.

Stdout is INFO only (no raw IRC, no AGPK/SEAL bodies). Full lines go to irc.log if
AGENTIC_IRC_DEBUG=1. SASL: AGENTIC_IRC_SASL_USER + AGENTIC_IRC_SASL_PASSWORD (not argv).
"""
from __future__ import annotations

import argparse
import base64
import os
import random
import socket
import ssl
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import filexfer  # noqa: E402
import moot  # noqa: E402
import protect  # noqa: E402
import seal  # noqa: E402
import wire  # noqa: E402

FLOOD_S = 0.8


def info(msg: str) -> None:
    print(msg, flush=True)


def debug_log(path: Path | None, line: str) -> None:
    if path is None:
        return
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


class Client:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.original_nick = args.nick
        self.live_nick = args.nick
        chan = args.channel if args.channel.startswith("#") else "#" + args.channel
        if "|" in chan:
            raise ValueError("channel must not contain |")
        self.chan = chan
        if args.home:
            os.environ["AGENTIC_IRC_HOME"] = str(Path(args.home).expanduser())
        self.home = seal.home()
        self.home.mkdir(parents=True, exist_ok=True)
        protect.protect_path(self.home)
        self.outbox = Path(args.outbox) if args.outbox else self.home / "outbox.txt"
        self.inbox = self.home / "inbox"
        self.inbox.mkdir(parents=True, exist_ok=True)
        protect.protect_path(self.inbox)
        self.debug = self.home / "irc.log" if os.environ.get("AGENTIC_IRC_DEBUG") else None
        self.ident = seal.load_ident() if seal.ident_path().exists() else None
        self.peers = seal.load_peers()
        self.fragments = seal.FragmentStore()
        self._moot: dict = {}
        self.file_bags = filexfer.FileBag()
        self.lock = threading.Lock()
        self.sock: ssl.SSLSocket | None = None
        self.ready = threading.Event()
        self.joined = threading.Event()
        self.dead = threading.Event()
        self.stop = threading.Event()
        self.sasl_ack = threading.Event()
        self.sasl_plus = threading.Event()
        self.sasl_903 = threading.Event()
        self.sasl_fail = threading.Event()

    def send(self, line: str) -> None:
        assert self.sock is not None
        with self.lock:
            self.sock.sendall((line + "\r\n").encode("utf-8"))

    def say(self, msg: str) -> None:
        self.send("PRIVMSG " + self.chan + " :" + msg)
        time.sleep(FLOOD_S)

    def connect(self) -> ssl.SSLSocket:
        ctx = ssl.create_default_context()
        raw = socket.create_connection((self.args.host, self.args.port), 20)
        raw.settimeout(None)
        sock = ctx.wrap_socket(raw, server_hostname=self.args.host)
        sock.settimeout(None)
        return sock

    def sasl_token(self) -> str | None:
        user = os.environ.get("AGENTIC_IRC_SASL_USER")
        pw = os.environ.get("AGENTIC_IRC_SASL_PASSWORD")
        if not user or not pw:
            return None
        return base64.b64encode(b"\0" + user.encode("utf-8") + b"\0" + pw.encode("utf-8")).decode("ascii")

    def sasl_on_line(self, cmd: str, args: list[str], trailing: str) -> list[str]:
        """Advance SASL. Returns lines to send. No network."""
        out: list[str] = []
        tokens = [a.lower() for a in args] + trailing.lower().split()
        if cmd == "CAP" and "ack" in tokens and "sasl" in tokens:
            self.sasl_ack.set()
            out.append("AUTHENTICATE PLAIN")
        if cmd == "AUTHENTICATE" and trailing.strip() == "+":
            self.sasl_plus.set()
            tok = self.sasl_token()
            if tok:
                out.append("AUTHENTICATE " + tok)
        if cmd == "903":
            self.sasl_903.set()
            out.append("CAP END")
        if cmd in ("902", "904", "905", "906", "907"):
            self.sasl_fail.set()
            out.append("CAP END")
        return out

    def sasl_plain(self) -> None:
        if not self.sasl_token():
            info("INFO no-sasl")
            return
        self.sasl_ack.clear()
        self.sasl_plus.clear()
        self.sasl_903.clear()
        self.sasl_fail.clear()
        self.send("CAP REQ :sasl")
        if not self.sasl_ack.wait(10):
            info("INFO no-sasl")
            self.send("CAP END")
            return
        if not self.sasl_plus.wait(10):
            info("INFO no-sasl")
            self.send("CAP END")
            return
        if self.sasl_fail.wait(0.01):
            info("INFO no-sasl")
            return
        if not self.sasl_903.wait(10):
            info("INFO no-sasl")
            self.send("CAP END")
            return

    def handle_capa(self, src: str, body: str) -> None:
        p = wire.parse_capa_line(body)
        if p:
            info(f"INFO capa from={src}")

    def handle_moot(self, src: str, body: str) -> None:
        ml = wire.parse_moot_line(body)
        if not ml:
            return
        self._moot = moot.apply_moot(self._moot, src, ml, self.home)
        if ml.verb == "OPEN":
            info(f"INFO moot OPEN id={ml.moot_id} chair={src}")

    def handle_file(self, src: str, body: str) -> None:
        fl = wire.parse_file_line(body)
        if not fl:
            return
        if fl.verb == "OFFER":
            name = fl.fields[-1] if fl.fields else ""
            nbytes = fl.fields[3] if len(fl.fields) > 3 else ""
            sha = fl.fields[4] if len(fl.fields) > 4 else ""
            tier = fl.fields[5] if len(fl.fields) > 5 else ""
            if not fl.file_id:
                return
            if not self.file_bags.note_offer(src, fl.file_id, name, sha, nbytes, tier):
                info(f"INFO file OFFER id={fl.file_id} ignored (duplicate)")
                return
            info(f"INFO file OFFER id={fl.file_id} name={name} bytes={nbytes}")
        if fl.verb == "CHUNK" and fl.chunk_b64 and fl.i and fl.n and fl.file_id:
            self.file_bags.add_chunk(src, fl.file_id, fl.i, fl.n, fl.chunk_b64)
        if fl.verb == "ABORT" and fl.file_id:
            self.file_bags.abort(fl.file_id)
            info(f"INFO file ABORT id={fl.file_id}")
        if fl.verb == "DONE" and fl.file_id:
            sha = fl.fields[1] if len(fl.fields) > 1 else ""
            data = self.file_bags.take_assembled(fl.file_id)
            offer = self.file_bags._offers.get(fl.file_id.lower(), {})
            name = offer.get("name") or "file.bin"
            expect = offer.get("sha") or sha
            if data is None:
                info(f"INFO file DONE id={fl.file_id} fail (incomplete)")
                return
            if filexfer.complete_write(self.home, fl.file_id, name, data, expect):
                info(f"INFO file DONE id={fl.file_id} ok")
            else:
                info(f"INFO file DONE id={fl.file_id} fail")

    def handle_dumb(self, src: str, body: str) -> None:
        dl = wire.parse_dumb_line(body)
        if not dl:
            return
        if dl.from_nick and dl.from_nick.lower() != src.lower():
            info("INFO DUMB prefix != from_nick, drop")
            return
        info(f"INFO dumb job id={dl.msg_id} from={src}")

    def handle_privmsg(self, prefix: str, target: str, body: str) -> None:
        if target.lower() != self.chan.lower():
            return
        src = prefix.split("!", 1)[0].lstrip(":")
        pk = seal.parse_agpk_line(body)
        if pk is not None:
            result = seal.tofu_pin(self.peers, src, pk)
            if result == "pinned":
                seal.save_peers(self.peers)
                info(f"INFO peer {src} AGPK pinned")
            elif result == "mismatch":
                info(f"INFO peer {src} AGPK mismatch (ignored)")
            return
        parsed = seal.parse_seal_line(body)
        if parsed is None:
            self.handle_capa(src, body)
            self.handle_moot(src, body)
            self.handle_file(src, body)
            self.handle_dumb(src, body)
            return
        if parsed.version == 2 and parsed.from_nick and parsed.from_nick.lower() != src.lower():
            info("INFO SEAL prefix != from_nick, drop")
            return
        mine = {self.original_nick.lower(), self.live_nick.lower()}
        if parsed.to_nick.lower() not in mine:
            return
        if parsed.version != 2:
            info(f"INFO SEAL {parsed.msg_id} v1 ignored")
            return
        payload = self.fragments.add(parsed)
        if payload is None:
            return
        if self.ident is None:
            info(f"INFO SEAL {parsed.msg_id} dropped (no identity)")
            return
        try:
            blob = seal.b64d(payload)
            if parsed.version == 2:
                from_nick = parsed.from_nick or src
                pin = self.peers.get(from_nick.lower(), {}).get("pk")
                if not pin:
                    info(f"INFO SEAL {parsed.msg_id} dropped (no AGPK pin for {from_nick})")
                    return
                pt = seal.open_bytes_v2(
                    blob, self.ident, self.chan, parsed.to_nick, from_nick, parsed.msg_id, pin
                )
            else:
                return
        except Exception as e:
            info(f"INFO SEAL {parsed.msg_id} decrypt failed {type(e).__name__}")
            return
        dest = self.inbox / f"{parsed.msg_id}.bin"
        if dest.exists():
            info(f"INFO SEAL {parsed.msg_id} inbox id exists, skip write")
            return
        dest.write_bytes(pt)
        protect.protect_path(dest)
        info(f"INFO SEAL {parsed.msg_id} -> inbox ({len(pt)} bytes)")

    def reader(self) -> None:
        assert self.sock is not None
        buf = b""
        try:
            while not self.stop.is_set():
                data = self.sock.recv(4096)
                if not data:
                    return
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    t = line.decode("utf-8", "replace").rstrip("\r")
                    debug_log(self.debug, t)
                    if t.startswith("PING "):
                        self.send("PONG " + t[5:])
                        continue
                    prefix = ""
                    rest = t
                    if t.startswith(":"):
                        prefix, _, rest = t[1:].partition(" ")
                    parts = rest.split(" ")
                    cmd = parts[0] if parts else ""
                    trailing = t.split(" :", 1)[1] if " :" in t else ""
                    if cmd == "001":
                        self.ready.set()
                    if cmd == "JOIN":
                        ch = parts[1].lstrip(":") if len(parts) > 1 else ""
                        if ch.lower() == self.chan.lower():
                            self.joined.set()
                    if cmd in ("433", "432"):
                        if self.live_nick == self.original_nick:
                            self.live_nick = self.original_nick + "_l"
                            self.send("NICK " + self.live_nick)
                            info(f"INFO nick -> {self.live_nick} (still accept {self.original_nick})")
                    for line in self.sasl_on_line(cmd, parts[1:], trailing):
                        self.send(line)
                    if cmd == "PRIVMSG" and " :" in t:
                        target = parts[1].lstrip(":") if len(parts) > 1 else ""
                        self.handle_privmsg(prefix, target, t.split(" :", 1)[1])
        except OSError:
            return
        finally:
            self.dead.set()

    def outbox_loop(self) -> None:
        path = self.outbox
        last = path.stat().st_size if path.exists() else 0
        while not self.stop.is_set() and not self.dead.is_set():
            if not self.joined.wait(timeout=1):
                continue
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
                if line and self.sock is not None:
                    try:
                        self.say(line)
                    except OSError:
                        return

    def session(self) -> None:
        self.ready.clear()
        self.joined.clear()
        self.dead.clear()
        self.live_nick = self.original_nick
        self.sock = self.connect()
        threading.Thread(target=self.reader, daemon=True).start()
        threading.Thread(target=self.outbox_loop, daemon=True).start()
        self.send("CAP LS 302")
        self.send("NICK " + self.live_nick)
        self.send(f"USER {self.live_nick} 0 * :{self.args.realname}")
        self.sasl_plain()
        if not self.ready.wait(30):
            raise TimeoutError("NO 001")
        time.sleep(1)
        self.send("JOIN " + self.chan)
        if not self.joined.wait(30):
            raise TimeoutError("NO JOIN")
        if self.args.hello:
            self.say(self.args.hello)
        if self.args.announce_key:
            if self.ident is None:
                info("INFO no identity; skip AGPK")
            else:
                self.say("AGPK v1 " + self.ident["pk"])
        info(f"INFO joined {self.chan} as {self.live_nick}")
        while not self.stop.is_set() and not self.dead.wait(timeout=1):
            pass

    def run_forever(self) -> None:
        backoff = 1.0
        while not self.stop.is_set():
            try:
                self.session()
                backoff = 1.0
            except Exception as e:
                info(f"INFO session end {type(e).__name__}")
            try:
                if self.sock:
                    self.sock.close()
            except OSError:
                pass
            self.sock = None
            delay = backoff + random.uniform(0, 1)
            info(f"INFO reconnect in {delay:.1f}s")
            time.sleep(delay)
            backoff = min(60.0, backoff * 2)


def main() -> None:
    import signal

    p = argparse.ArgumentParser(description="agentic TLS IRC")
    p.add_argument("--host", default="irc.libera.chat")
    p.add_argument("--port", type=int, default=6697)
    p.add_argument("--nick", required=True)
    p.add_argument("--channel", required=True)
    p.add_argument("--home", default="", help="AGENTIC_IRC_HOME (required if two nicks on one box)")
    p.add_argument("--realname", default="agentic-irc")
    p.add_argument("--outbox", default="")
    p.add_argument("--hello", default="")
    p.add_argument("--announce-key", action="store_true")
    p.add_argument("--once", action="store_true", help="no reconnect (tests)")
    args = p.parse_args()
    c = Client(args)

    def _stop(*_a: object) -> None:
        c.stop.set()

    signal.signal(signal.SIGINT, _stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _stop)
    if args.once:
        c.session()
        return
    c.run_forever()


if __name__ == "__main__":
    main()
