#!/usr/bin/env python3
"""Python dumb connector: jail + allowlisted exec/get/put. No LLM. Offline-testable."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import socket
import ssl
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import protect
import seal
import wire

DEFAULT_BINS = frozenset({"cmd.exe", "powershell.exe", "hostname.exe", "ipconfig.exe", "whoami.exe", "hostname", "ipconfig", "whoami"})
META_CHARS = frozenset("&|><^")
FLOOD_S = 0.8
CAPA_S = 600.0
SETTLE_S = 1.0
RESULT_BYTES_MAX = 8192
_busy = threading.Lock()


def info(msg: str) -> None:
    print(msg, flush=True)


def debug_log(path: Path | None, line: str) -> None:
    if path is None:
        return
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def jail_root(allow: str) -> Path:
    p = Path(allow).resolve()
    p.mkdir(parents=True, exist_ok=True)
    protect.protect_path(p)
    return p


def in_jail(root: Path, target: Path) -> bool:
    try:
        raw = str(target)
        if raw.startswith("\\\\") or raw.startswith("//"):
            return False
        t = target.resolve()
        r = root.resolve()
        ts, rs = str(t), str(r)
        if ts.startswith("\\\\") or ts.startswith("//"):
            return False
        return r == t or r in t.parents
    except Exception:
        return False


def _spill_results(home: Path, jid: str, out: str, err: str) -> None:
    dest = Path(home) / "dumb" / "results" / f"{jid}.txt"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(f"--- stdout ---\n{out}\n--- stderr ---\n{err}\n", encoding="utf-8", errors="replace")
    protect.protect_path(dest)


def run_job(
    job: dict,
    *,
    operators: set[str],
    from_nick: str,
    allow_path: Path,
    allow_bin: set[str],
    allow_meta: bool = False,
    home: Path | None = None,
) -> dict:
    if from_nick.lower() not in {x.lower() for x in operators}:
        return {"v": 1, "op": job.get("op"), "id": job.get("id"), "ok": False, "error": "operator"}
    op = job.get("op")
    jid = job.get("id", "")
    if op == "ping":
        return {"v": 1, "op": "ping", "id": jid, "ok": True, "rc": 0}
    if op == "sysinfo":
        return {
            "v": 1,
            "op": "sysinfo",
            "id": jid,
            "ok": True,
            "sys": {"os": sys.platform, "machine": os.environ.get("COMPUTERNAME", ""), "user": os.environ.get("USERNAME", "")},
        }
    if op in {"get", "put"}:
        raw = job.get("path") or job.get("cwd") or ""
        if str(raw).startswith("\\\\") or str(raw).startswith("//"):
            return {"v": 1, "op": op, "id": jid, "ok": False, "error": "jail"}
        dest = Path(raw)
        if not dest.is_absolute():
            dest = allow_path / dest
        if not in_jail(allow_path, dest):
            return {"v": 1, "op": op, "id": jid, "ok": False, "error": "jail"}
        if dest.name in {"identity.json", "connector.key", "peers.json"}:
            return {"v": 1, "op": op, "id": jid, "ok": False, "error": "jail"}
        if op == "get":
            data = dest.read_bytes()
            return {"v": 1, "op": "get", "id": jid, "ok": True, "sha256": hashlib.sha256(data).hexdigest(), "b64": seal.b64(data) if len(data) <= 12 * 1024 else ""}
        raw_b = seal.b64d(job.get("b64", "")) if job.get("b64") else b""
        dest.write_bytes(raw_b)
        return {"v": 1, "op": "put", "id": jid, "ok": True, "sha256": hashlib.sha256(raw_b).hexdigest()}
    if op == "exec":
        if not _busy.acquire(blocking=False):
            return {"v": 1, "op": "exec", "id": jid, "ok": False, "error": "busy"}
        try:
            argv = job.get("argv") or []
            if not argv:
                return {"v": 1, "op": "exec", "id": jid, "ok": False, "error": "bin"}
            bin0 = Path(str(argv[0])).name.lower()
            if bin0 not in {x.lower() for x in allow_bin}:
                return {"v": 1, "op": "exec", "id": jid, "ok": False, "error": "bin"}
            joined = " ".join(str(x) for x in argv)
            if any(tok in joined for tok in ("..", "\\\\", "//")):
                return {"v": 1, "op": "exec", "id": jid, "ok": False, "error": "jail"}
            if not allow_meta and any(ch in joined for ch in META_CHARS):
                return {"v": 1, "op": "exec", "id": jid, "ok": False, "error": "bin"}
            timeout = int(job.get("timeout_s") or 20)
            timeout = max(1, min(60, timeout))
            cwd = job.get("cwd") or str(allow_path)
            if str(cwd).startswith("\\\\") or str(cwd).startswith("//"):
                return {"v": 1, "op": "exec", "id": jid, "ok": False, "error": "jail"}
            if not in_jail(allow_path, Path(cwd)):
                return {"v": 1, "op": "exec", "id": jid, "ok": False, "error": "jail"}
            runner = job.get("_runner") if callable(job.get("_runner")) else None
            if runner:
                rc, out, err = runner(argv, cwd, timeout)
            else:
                p = subprocess.run(argv, cwd=cwd, capture_output=True, timeout=timeout, text=True)
                rc, out, err = p.returncode, p.stdout or "", p.stderr or ""
            trunc = False
            if len(out) + len(err) > RESULT_BYTES_MAX:
                trunc = True
                if home and jid:
                    _spill_results(home, str(jid), out, err)
                out, err = out[:4000], err[:4000]
            return {"v": 1, "op": "exec", "id": jid, "ok": rc == 0, "rc": rc, "stdout": out, "stderr": err, "truncated": trunc}
        except subprocess.TimeoutExpired:
            return {"v": 1, "op": "exec", "id": jid, "ok": False, "error": "timeout"}
        finally:
            _busy.release()
    return {"v": 1, "op": op, "id": jid, "ok": False, "error": "op"}


def handle_dumb_payload(
    body: bytes,
    *,
    channel: str,
    to_nick: str,
    from_nick: str,
    msg_id: str,
    key32: bytes,
    operators: set[str],
    allow_path: Path,
    allow_bin: set[str] | None = None,
    allow_meta: bool = False,
    home: Path | None = None,
) -> dict:
    pt = seal.dumb_open_bytes(body, key32, channel, to_nick, from_nick, msg_id)
    job = json.loads(pt.decode("utf-8"))
    return run_job(
        job,
        operators=operators,
        from_nick=from_nick,
        allow_path=allow_path,
        allow_bin=allow_bin or DEFAULT_BINS,
        allow_meta=allow_meta,
        home=home,
    )


def _parse_operators(raw: str) -> set[str]:
    return {x.strip() for x in raw.split(",") if x.strip()}


class Client:
    """stdlib socket+ssl connector. Tests inject connect() / handle_privmsg; no Libera from pytest."""

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
        self.debug = self.home / "irc.log" if os.environ.get("AGENTIC_IRC_DEBUG") else None
        self.operators = _parse_operators(getattr(args, "operators", "") or "")
        if not self.operators:
            raise SystemExit("installer MUST refuse empty --operators")
        self.allow_path = jail_root(args.allow_path)
        extra = getattr(args, "allow_bin", "") or ""
        self.allow_bin = set(DEFAULT_BINS)
        if extra.strip():
            self.allow_bin |= {x.strip() for x in extra.split(",") if x.strip()}
        self.allow_meta = bool(getattr(args, "allow_meta", False))
        self.key: bytes | None = None
        kp = self.home / "dumb" / "connector.key"
        if kp.exists():
            self.key = protect.read_secret_bytes(kp)
        self.fragments = seal.FragmentStore()
        self.lock = threading.Lock()
        self.sock: ssl.SSLSocket | socket.socket | None = None
        self.sent: list[str] = []
        self.ready = threading.Event()
        self.joined = threading.Event()
        self.dead = threading.Event()
        self.stop = threading.Event()

    def capa_line(self) -> str:
        psk = "1" if self.key else "0"
        jail = str(self.allow_path)
        return (
            f"CAPA v1 dumb nick={self.original_nick} "
            f"verbs=ping,sysinfo,exec,get,put psk={psk} agpk=0 jail={jail}"
        )

    def send(self, line: str) -> None:
        self.sent.append(line)
        if self.sock is None:
            return
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

    def handle_dumb(self, src: str, body: str) -> None:
        dl = wire.parse_dumb_line(body)
        if not dl:
            return
        if dl.from_nick and dl.from_nick.lower() != src.lower():
            info("INFO DUMB prefix != from_nick, drop")
            return
        mine = {self.original_nick.lower(), self.live_nick.lower()}
        if dl.to_nick.lower() not in mine:
            return
        if src.lower() not in {x.lower() for x in self.operators}:
            info(f"INFO dumb drop operator from={src}")
            return
        payload = self.fragments.add(dl)
        if payload is None:
            return
        if not self.key:
            info(f"INFO dumb job id={dl.msg_id} decrypt failed")
            return
        try:
            blob = seal.b64d(payload)
            pt = seal.dumb_open_bytes(blob, self.key, self.chan, dl.to_nick, src, dl.msg_id)
            job = json.loads(pt.decode("utf-8"))
        except Exception:
            info(f"INFO dumb job id={dl.msg_id} decrypt failed")
            return
        result = run_job(
            job,
            operators=self.operators,
            from_nick=src,
            allow_path=self.allow_path,
            allow_bin=self.allow_bin,
            allow_meta=self.allow_meta,
            home=self.home,
        )
        rid = str(job.get("id") or dl.msg_id)
        out_blob = seal.dumb_seal_bytes(
            json.dumps(result).encode("utf-8"),
            self.key,
            self.chan,
            src,
            self.original_nick,
            rid,
        )
        for ln in seal.dumb_irc_lines(out_blob, src, self.original_nick, rid):
            self.say(ln)
        info(f"INFO dumb job id={dl.msg_id} op={job.get('op')} from={src}")

    def handle_privmsg(self, prefix: str, target: str, body: str) -> None:
        if target.lower() != self.chan.lower():
            return
        src = prefix.split("!", 1)[0].lstrip(":")
        self.handle_dumb(src, body)

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
                    if cmd == "PRIVMSG" and " :" in t:
                        target = parts[1].lstrip(":") if len(parts) > 1 else ""
                        self.handle_privmsg(prefix, target, t.split(" :", 1)[1])
        except OSError:
            return
        finally:
            self.dead.set()

    def session(self) -> None:
        self.ready.clear()
        self.joined.clear()
        self.dead.clear()
        self.live_nick = self.original_nick
        self.sock = self.connect()
        threading.Thread(target=self.reader, daemon=True).start()
        self.send("CAP LS 302")
        self.send("NICK " + self.live_nick)
        realname = getattr(self.args, "realname", None) or "airc-dumb"
        self.send(f"USER {self.live_nick} 0 * :{realname}")
        if not self.ready.wait(30):
            raise TimeoutError("NO 001")
        time.sleep(SETTLE_S)
        self.send("JOIN " + self.chan)
        if not self.joined.wait(30):
            raise TimeoutError("NO JOIN")
        if getattr(self.args, "hello", ""):
            self.say(self.args.hello)
        self.say(self.capa_line())
        info(f"INFO joined {self.chan} as {self.live_nick}")
        last_capa = time.time()
        while not self.stop.is_set() and not self.dead.wait(timeout=1):
            if time.time() - last_capa >= CAPA_S:
                self.say(self.capa_line())
                last_capa = time.time()

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

    p = argparse.ArgumentParser()
    p.add_argument("--nick", required=True)
    p.add_argument("--channel", required=True)
    p.add_argument("--home", required=True)
    p.add_argument("--operators", required=True)
    p.add_argument("--allow-path", required=True)
    p.add_argument("--hello", default="")
    p.add_argument("--host", default="irc.libera.chat")
    p.add_argument("--port", type=int, default=6697)
    p.add_argument("--realname", default="airc-dumb")
    p.add_argument("--once", action="store_true", help="no reconnect (tests)")
    p.add_argument("--allow-meta", action="store_true")
    p.add_argument("--allow-bin", default="")
    args = p.parse_args()
    if not args.operators.strip():
        raise SystemExit("installer MUST refuse empty --operators")
    os.environ["AGENTIC_IRC_HOME"] = args.home
    info(f"INFO dumb connector {args.nick} jail={args.allow_path}")
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
