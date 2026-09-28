#!/usr/bin/env python3
"""Live IRC host for airc console service (FR #253).

Nick ``console`` on ``#{machinename}``, register/identify, silent in channel,
authenticated PRIVMSG → per-user console pipe. Designed to run under NSSM.
"""
from __future__ import annotations

import argparse
import base64
import os
import socket
import ssl
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from account_map import AccountMap, account_from_tags, parse_message_tags, parse_prefix_nick
from airc_console import (
    AircConsoleCore,
    AuthPolicy,
    ConsoleSessionManager,
    console_nick,
    ensure_nickserv_password,
    home_dir,
    load_operators,
    machine_id,
    resolve_server_password,
    shop_channel,
)

FLOOD_S = 0.35


def info(msg: str) -> None:
    print(msg, flush=True)


def read_password(path: Path | None, env_key: str = "AIRC_CONSOLE_PASSWORD") -> str | None:
    """Legacy helper — prefer resolve_server_password / ensure_nickserv_password (#271)."""
    for key in (env_key, "AGENTIC_IRC_PASSWORD", "AIRC_CONSOLE_SERVER_PASSWORD"):
        env = os.environ.get(key)
        if env and env.strip():
            return env.strip()
    if path and path.is_file():
        return path.read_text(encoding="utf-8").strip() or None
    return None


class AircConsoleService:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.home = home_dir(args.home)
        self.home.mkdir(parents=True, exist_ok=True)
        self.machine = machine_id(args.machine)
        self.channel = shop_channel(self.machine)
        # #286: default console-<machine> — bare "console" gets 433 on shared Ergo.
        self.nick = console_nick(self.machine, getattr(args, "nick", None))
        self._nick_retries = 0
        # #271: NickServ GUID in console.password (mint+reuse). Ergo PASS separate.
        nickserv_path = (
            Path(args.password_file)
            if args.password_file
            else (self.home / "console.password")
        )
        self.nickserv_password = ensure_nickserv_password(nickserv_path, mint=True)
        self.password = self.nickserv_password  # SASL / identify use NickServ secret
        self.server_password = resolve_server_password(
            home=self.home,
            password_file=Path(args.password_file) if args.password_file else None,
        )
        if self.nickserv_password:
            info(f"INFO nickserv-password file={nickserv_path} (GUID store+reuse)")
        if self.server_password:
            info("INFO server PASS available (env/ergo.password)")
        else:
            info("INFO no-server-pass (set AGENTIC_IRC_PASSWORD or ergo.password)")
        ops = load_operators(
            Path(args.operators_file) if args.operators_file else self.home / "operators.txt",
            args.operators,
        )
        accts = {x.strip().lower() for x in (args.accounts or []) if x.strip()}
        amap = AccountMap()
        amap_path = self.home / "accounts.json"
        amap.load(amap_path)
        self.account_map = amap
        self.amap_path = amap_path
        auth = AuthPolicy(
            operators=ops,
            accounts=accts,
            account_map=amap,
            require_account=bool(args.require_account or accts),
        )
        if not ops and not accts:
            raise SystemExit("airc console: refuse empty operators/accounts (FR #253)")
        self.sessions = ConsoleSessionManager(
            shell=args.shell,
            cwd=args.cwd or str(self.home),
            on_output=self._on_console_out,
            idle_sec=float(args.idle_sec),
        )
        self.core = AircConsoleCore(
            machine=self.machine,
            auth=auth,
            sessions=self.sessions,
            nick=self.nick,
        )
        self.sock: ssl.SSLSocket | socket.socket | None = None
        self._send_lock = threading.Lock()
        self._stop = threading.Event()

    def _on_console_out(self, nick: str, line: str) -> None:
        # Reply in Query only — never on shop channel (silent).
        self.send_privmsg(nick, line[:400])

    def connect(self) -> None:
        raw = socket.create_connection((self.args.host, int(self.args.port)), timeout=30)
        if self.args.tls:
            ctx = ssl.create_default_context()
            if self.args.tls_insecure:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            self.sock = ctx.wrap_socket(raw, server_hostname=self.args.host)
        else:
            self.sock = raw
        self.sock.settimeout(1.0)
        info(f"INFO connected {self.args.host}:{self.args.port} tls={self.args.tls}")

    def send(self, line: str) -> None:
        if not self.sock:
            return
        data = (line.rstrip("\r\n") + "\r\n").encode("utf-8", errors="replace")
        with self._send_lock:
            self.sock.sendall(data)
            time.sleep(FLOOD_S)

    def send_privmsg(self, target: str, text: str) -> None:
        if self.core.may_speak_on_channel() is False and target.lower() == self.channel.lower():
            info(f"INFO drop channel speak target={target}")
            return
        # IRC line length safety
        safe = text.replace("\n", " ").replace("\r", " ")
        self.send(f"PRIVMSG {target} :{safe}")

    def send_server_pass(self) -> None:
        """Ergo irc.ntsa.uk requires PASS before NICK/USER (same as irc_agent)."""
        if not self.server_password:
            info("INFO no-server-pass (set AGENTIC_IRC_PASSWORD / ergo.password)")
            return
        self.send("PASS " + self.server_password)
        info("INFO sent server PASS")

    def request_caps(self) -> None:
        # account-tag powers operator account allowlists (FR #230). SASL is best-effort.
        caps = "account-notify extended-join account-tag"
        if self.nickserv_password and self.args.sasl:
            caps = "sasl " + caps
            self._want_sasl = True
        else:
            self._want_sasl = False
        self.send(f"CAP REQ :{caps}")

    def sasl_plain(self) -> None:
        if not self.nickserv_password or not self.args.sasl:
            return
        # Minimal PLAIN; failures must CAP END so registration can proceed.
        self._want_sasl = True

    def register_or_identify(self) -> None:
        """Best-effort NickServ identify/register with stored GUID (#271)."""
        if not self.nickserv_password:
            info("INFO skip nick register/identify (no nickserv password)")
            return
        # Ergo may have services disabled; ignore failures in read loop.
        self.send(f"PRIVMSG NickServ :IDENTIFY {self.nick} {self.nickserv_password}")
        self.send(
            f"PRIVMSG NickServ :REGISTER {self.nickserv_password} console@{self.machine}.local"
        )

    def handshake(self) -> None:
        self._want_sasl = False
        self._sasl_done = False
        # Order matches irc_agent: PASS → CAP → NICK/USER → (SASL) → CAP END.
        self.send_server_pass()
        self.request_caps()
        for cmd in self.core.register_commands():
            self.send(cmd)
        if self._want_sasl:
            self.sasl_plain()
        else:
            self.send("CAP END")
        self.register_or_identify()

    def join_shop(self) -> None:
        for cmd in self.core.join_commands():
            self.send(cmd)
        info(f"INFO joined {self.channel} as {self.nick} (silent)")

    def _handle_sasl_line(self, cmd: str, args: list[str], trailing: str) -> None:
        tokens = [a.lower() for a in args] + ([trailing.lower()] if trailing else [])
        if cmd == "CAP" and "ack" in tokens and "sasl" in " ".join(tokens) and self.nickserv_password:
            tok = base64.b64encode(
                f"{self.nick}\0{self.nick}\0{self.nickserv_password}".encode()
            ).decode("ascii")
            self.send("AUTHENTICATE PLAIN")
            self.send(f"AUTHENTICATE {tok}")
            return
        if cmd == "CAP" and "ack" in tokens and not self._want_sasl:
            self.send("CAP END")
            return
        if cmd == "903":
            self._sasl_done = True
            self.send("CAP END")
            return
        if cmd in {"904", "905", "906", "907"}:
            info(f"INFO sasl-fail {cmd} (continuing with server PASS)")
            self.send("CAP END")
            return

    def on_line(self, line: str) -> None:
        tags, rest = parse_message_tags(line)
        if rest.startswith("PING "):
            self.send("PONG " + rest[5:])
            return
        parts = rest.split(" ", 2)
        prefix = ""
        if rest.startswith(":"):
            try:
                prefix, rest2 = rest[1:].split(" ", 1)
            except ValueError:
                return
            rest = rest2
        bits = rest.split(" ")
        cmd = bits[0].upper() if bits else ""
        args = bits[1:]
        trailing = ""
        if " :" in rest:
            _, trailing = rest.split(" :", 1)
            args = rest.split(" :", 1)[0].split(" ")[1:]

        if cmd in {"CAP", "AUTHENTICATE", "903", "904", "905", "906", "907"} or (
            cmd == "CAP"
        ):
            self._handle_sasl_line(cmd, args, trailing)

        if cmd == "001":
            # Welcome — registration succeeded; JOIN shop channel.
            self.join_shop()

        if cmd == "433":
            # Nickname already in use — never get 001/JOIN without recovery (#286).
            self._nick_retries += 1
            if self._nick_retries > 5:
                info(f"INFO nick-collision giving up on {self.nick}")
                return
            alt = console_nick(self.machine, None)
            if self.nick.lower() == alt.lower():
                alt = f"{alt}-{self._nick_retries}"[:30]
            info(f"INFO nick-in-use 433 {self.nick} -> {alt}")
            self.nick = alt
            self.core.nick = alt
            self.send(f"NICK {alt}")
            return

        if cmd == "JOIN":
            nick = parse_prefix_nick(":" + prefix) if prefix else None
            # extended-join: JOIN #chan account :gecos
            acct = None
            if len(args) >= 2 and args[1] and not args[1].startswith("#") and args[1] != "*":
                acct = args[1]
            if nick and acct:
                self.account_map.set(nick, acct)
                self.account_map.save(self.amap_path)

        acct_tag = account_from_tags(tags)
        if acct_tag and prefix:
            nick = parse_prefix_nick(":" + prefix) or prefix.split("!")[0]
            self.account_map.set(nick, acct_tag)
            self.account_map.save(self.amap_path)

        hr = self.core.handle_raw(line)
        if not hr:
            return
        if hr.action == "deny" and hr.nick and hr.reply:
            self.send_privmsg(hr.nick, hr.reply)
        elif hr.action in {"help", "close"} and hr.nick and hr.reply:
            self.send_privmsg(hr.nick, hr.reply)
        elif hr.action == "pipe":
            info(f"INFO pipe from={hr.nick}")

    def read_loop(self) -> None:
        assert self.sock is not None
        buf = b""
        while not self._stop.is_set():
            try:
                chunk = self.sock.recv(4096)
                    except (socket.timeout, TimeoutError):
                # Python 3.10+ ssl may raise TimeoutError; keep the loop alive (#286).
                try:
                    self.sessions.reap_idle()
                except Exception as re:
                    info(f"INFO reap-err {re}")
                continue
            except Exception as e:
                info(f"INFO recv-err {e}")
                break
            if not chunk:
                info("INFO eof")
                break
            buf += chunk
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                line = raw.decode("utf-8", errors="replace").rstrip("\r")
                if line:
                    try:
                        self.on_line(line)
                    except Exception as e:
                        info(f"INFO on_line-err {e}")

    def run(self) -> int:
        info(f"INFO airc-console machine={self.machine} channel={self.channel} nick={self.nick}")
        backoff = 5
        while not self._stop.is_set():
            try:
                self.connect()
                self.handshake()
                self.read_loop()
            except Exception as e:
                info(f"INFO session-err {e}")
            finally:
                self.sessions.close_all()
                if self.sock:
                    try:
                        self.sock.close()
                    except Exception:
                        pass
                    self.sock = None
            if self._stop.is_set():
                break
            info(f"INFO reconnect in {backoff}s")
            time.sleep(backoff)
            backoff = min(60, backoff * 2)
        return 0


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="airc console Windows service host (FR #253)")
    p.add_argument("--host", default=os.environ.get("AIRC_IRC_HOST", "irc.ntsa.uk"))
    p.add_argument("--port", type=int, default=int(os.environ.get("AIRC_IRC_PORT", "6697")))
    p.add_argument("--tls", action="store_true", default=True)
    p.add_argument("--no-tls", action="store_false", dest="tls")
    p.add_argument("--tls-insecure", action="store_true")
    p.add_argument(
        "--nick",
        default="auto",
        help="IRC nick (default auto = console-<machine>; bare 'console' collides on shared Ergo #286)",
    )
    p.add_argument("--machine", default=None, help="override COMPUTERNAME for #{machine}")
    p.add_argument("--home", default=None)
    p.add_argument("--password-file", default=None)
    p.add_argument(
        "--sasl",
        action="store_true",
        default=False,
        help="attempt SASL PLAIN after server PASS (default off; Ergo fleet uses PASS)",
    )
    p.add_argument("--operators", nargs="*", default=[])
    p.add_argument("--operators-file", default=None)
    p.add_argument("--accounts", nargs="*", default=[], help="services account allowlist")
    p.add_argument("--require-account", action="store_true")
    p.add_argument("--shell", default=None)
    p.add_argument("--cwd", default=None)
    p.add_argument("--idle-sec", type=float, default=3600.0)
    p.add_argument("--selftest", action="store_true", help="offline smoke then exit 0")
    return p


def selftest() -> int:
    mid = machine_id("IONOS")
    assert shop_channel(mid) == "#ionos", shop_channel(mid)
    assert console_nick("IONOS") == "console-ionos"
    assert console_nick("IONOS", "auto") == "console-ionos"
    assert console_nick("IONOS", "console") == "console"
    auth = AuthPolicy(operators={"simon"}, accounts=set())
    assert auth.allow("Simon")
    assert not auth.allow("stranger")
    core = AircConsoleCore(machine="ionos", auth=auth, sessions=ConsoleSessionManager(on_output=None))
    assert core.may_speak_on_channel() is False
    r = core.handle_raw(":evil!e@h PRIVMSG #ionos :whoami")
    assert r and r.action == "silent_channel"
    r2 = core.handle_raw(":evil!e@h PRIVMSG console :whoami")
    assert r2 and r2.action == "deny"
    info("INFO selftest ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.selftest:
        return selftest()
    return AircConsoleService(args).run()


if __name__ == "__main__":
    raise SystemExit(main())
