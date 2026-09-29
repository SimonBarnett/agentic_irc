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
    domain_id,
    ensure_nickserv_password,
    home_dir,
    load_operators,
    lobby_channel,
    lobby_nick,
    machine_id,
    parse_chanserv_registered,
    resolve_server_password,
    shop_channel,
    shop_console_nick,
)

FLOOD_S = 0.35
# Issue #298: half-open / silent link detection + reconnect.
IDLE_PING_S = 60.0
IDLE_DEAD_S = 120.0
RECONNECT_MIN_S = 3.0
RECONNECT_MAX_S = 60.0
# FR #314: ChanServ INFO probe for shop vs domain lobby.
CHANSERV_PROBE_S = 8.0


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
        self.domain = domain_id(getattr(args, "domain", None))
        # FR #314: channel/nick finalized after ChanServ probe (unless overrides).
        explicit_nick = getattr(args, "nick", None)
        explicit_chan = getattr(args, "channel", None)
        self._nick_override = bool(
            explicit_nick
            and str(explicit_nick).strip()
            and str(explicit_nick).strip().lower() not in {"auto", ""}
        )
        self._channel_override = bool(explicit_chan and str(explicit_chan).strip())
        if self._channel_override:
            ch = str(explicit_chan).strip()
            self.channel = ch if ch.startswith("#") else f"#{ch}"
        else:
            self.channel = shop_channel(self.machine)  # provisional until probe
        # Handshake nick: shop console nick (or explicit). Lobby may NICK-change after probe.
        self.nick = console_nick(self.machine, explicit_nick)
        self._nick_retries = 0
        self._lobby_collision = 0
        self._mode: str | None = None  # 'shop' | 'lobby' | 'override'
        self._awaiting_chanserv = False
        self._chanserv_deadline = 0.0
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
            machine=self.machine,
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
        self._registered = False
        self._last_recv = 0.0
        self._last_ping_sent = 0.0
        self._awaiting_pong = False
        self._force_reconnect = False

    def _on_console_out(self, nick: str, line: str) -> None:
        # Reply in Query only — never on shop channel (silent).
        self.send_privmsg(nick, line[:400])

    def connect(self) -> None:
        self._registered = False
        self._force_reconnect = False
        self._awaiting_pong = False
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
        self._last_recv = time.monotonic()
        info(f"INFO connected {self.args.host}:{self.args.port} tls={self.args.tls}")

    def send(self, line: str) -> None:
        if not self.sock:
            raise ConnectionError("send: no socket")
        data = (line.rstrip("\r\n") + "\r\n").encode("utf-8", errors="replace")
        with self._send_lock:
            try:
                self.sock.sendall(data)
            except OSError as e:
                raise ConnectionError(f"send failed: {e}") from e
            time.sleep(FLOOD_S)

    def send_privmsg(self, target: str, text: str) -> None:
        if self.core.may_speak_on_channel() is False and target.lower() == self.channel.lower():
            info(f"INFO drop channel speak target={target}")
            return
        # IRC line length safety
        safe = text.replace("\n", " ").replace("\r", " ")
        self.send(f"PRIVMSG {target} :{safe}")

    def send_notice(self, target: str, text: str) -> None:
        """NOTICE — used for ping replies (including channel ping → Query-style NOTICE)."""
        safe = text.replace("\n", " ").replace("\r", " ")
        self.send(f"NOTICE {target} :{safe}")

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
        self.core.channel = self.channel
        self.core.nick = self.nick
        for cmd in self.core.join_commands():
            self.send(cmd)
        info(f"INFO joined {self.channel} as {self.nick} mode={self._mode or 'shop'} (silent)")

    def _start_chanserv_probe(self) -> None:
        """FR #314: INFO #{machine} then pick shop vs domain lobby."""
        if self._nick_override or self._channel_override:
            self._mode = "override"
            self.join_shop()
            return
        shop = shop_channel(self.machine)
        self._awaiting_chanserv = True
        self._chanserv_deadline = time.monotonic() + CHANSERV_PROBE_S
        info(f"INFO chanserv-probe INFO {shop} (timeout {CHANSERV_PROBE_S:.0f}s)")
        self.send(f"PRIVMSG ChanServ :INFO {shop}")

    def _apply_shop_mode(self) -> None:
        self._awaiting_chanserv = False
        self._mode = "shop"
        self.channel = shop_channel(self.machine)
        want = shop_console_nick(self.machine)
        if self.nick.lower() != want.lower():
            self.nick = want
            self.core.nick = want
            self.send(f"NICK {want}")
        info(f"INFO mode=shop channel={self.channel} nick={self.nick}")
        self.join_shop()

    def _apply_lobby_mode(self, reason: str) -> None:
        self._awaiting_chanserv = False
        self._mode = "lobby"
        self.channel = lobby_channel(self.domain)
        self._lobby_collision = 0
        want = lobby_nick(self.machine, 0)
        if self.nick.lower() != want.lower():
            self.nick = want
            self.core.nick = want
            self.send(f"NICK {want}")
        info(f"INFO mode=lobby reason={reason} channel={self.channel} nick={self.nick}")
        self.join_shop()

    def _on_chanserv_notice(self, text: str) -> bool:
        """Handle ChanServ NOTICE during probe. True if consumed."""
        if not self._awaiting_chanserv:
            return False
        verdict = parse_chanserv_registered(text)
        info(f"INFO chanserv-reply verdict={verdict} text={text[:160]}")
        if verdict is True:
            self._apply_shop_mode()
            return True
        if verdict is False:
            self._apply_lobby_mode("not-registered")
            return True
        return False

    def _chanserv_probe_tick(self) -> None:
        if not self._awaiting_chanserv:
            return
        if time.monotonic() >= self._chanserv_deadline:
            info("INFO chanserv-probe timeout → lobby")
            self._apply_lobby_mode("timeout")

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
        self._last_recv = time.monotonic()
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

        if cmd == "ERROR":
            info(f"INFO server-ERROR {trailing or ' '.join(args)}")
            self._force_reconnect = True
            return

        if cmd == "PONG":
            self._awaiting_pong = False
            return

        if cmd in {"CAP", "AUTHENTICATE", "903", "904", "905", "906", "907"} or (
            cmd == "CAP"
        ):
            self._handle_sasl_line(cmd, args, trailing)

        if cmd == "001":
            # Welcome — then ChanServ probe (FR #314) before JOIN.
            self._registered = True
            self._nick_retries = 0
            self._start_chanserv_probe()

        if cmd == "NOTICE" and prefix.lower().startswith("chanserv!"):
            if self._on_chanserv_notice(trailing or " ".join(args)):
                return

        if cmd == "433":
            # Nickname already in use — recover so we can still get 001/JOIN.
            self._nick_retries += 1
            if self._nick_retries > 8:
                info(f"INFO nick-collision giving up on {self.nick}")
                self._force_reconnect = True
                return
            if self._mode == "lobby" or (
                self._awaiting_chanserv is False and self._mode is None and not self._nick_override
            ):
                # FR #314 lobby: {machine}_1, _2, …
                self._lobby_collision = max(self._lobby_collision, 0) + 1
                alt = lobby_nick(self.machine, self._lobby_collision)
            else:
                alt = shop_console_nick(self.machine)
                if self.nick.lower() == alt.lower():
                    alt = f"{alt}_{self._nick_retries}"[:30]
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
        if hr.action == "ctcp_pong" and hr.nick is not None:
            # CTCP PONG via NOTICE (standard); works for client /ping flam*
            payload = hr.reply if hr.reply is not None else ""
            body = f"\x01PING {payload}\x01" if payload != "" else "\x01PING\x01"
            self.send_notice(hr.nick, body)
            info(f"INFO ctcp-pong to={hr.nick}")
        elif hr.action == "pong" and hr.nick and hr.reply:
            # Channel or Query "ping flam*" → NOTICE (not channel PRIVMSG).
            self.send_notice(hr.nick, hr.reply)
            info(f"INFO pong to={hr.nick} {hr.reply}")
        elif hr.action == "deny" and hr.nick and hr.reply:
            self.send_privmsg(hr.nick, hr.reply)
        elif hr.action in {"help", "close"} and hr.nick and hr.reply:
            self.send_privmsg(hr.nick, hr.reply)
        elif hr.action == "pipe":
            info(f"INFO pipe from={hr.nick}")

    def _idle_keepalive(self) -> None:
        """Detect half-open links: client PING, then force reconnect if no traffic (#298)."""
        now = time.monotonic()
        idle = now - self._last_recv
        if self._awaiting_pong and (now - self._last_ping_sent) >= IDLE_DEAD_S:
            info("INFO idle-dead (no PONG/traffic); reconnecting")
            self._force_reconnect = True
            return
        if self._registered and idle >= IDLE_PING_S and not self._awaiting_pong:
            token = str(int(time.time()))
            try:
                self.send(f"PING :{token}")
            except ConnectionError as e:
                info(f"INFO keepalive-send-err {e}")
                self._force_reconnect = True
                return
            self._last_ping_sent = now
            self._awaiting_pong = True
            info("INFO keepalive PING sent")

    def read_loop(self) -> None:
        assert self.sock is not None
        buf = b""
        while not self._stop.is_set() and not self._force_reconnect:
            try:
                chunk = self.sock.recv(4096)
            except (socket.timeout, TimeoutError):
                # Python 3.10+ ssl may raise TimeoutError; keep the loop alive (#286).
                try:
                    self.sessions.reap_idle()
                except Exception as re:
                    info(f"INFO reap-err {re}")
                try:
                    self._chanserv_probe_tick()
                    self._idle_keepalive()
                except Exception as ke:
                    info(f"INFO keepalive-err {ke}")
                    self._force_reconnect = True
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
                    except ConnectionError as e:
                        info(f"INFO on_line-conn-err {e}")
                        self._force_reconnect = True
                        break
                    except Exception as e:
                        info(f"INFO on_line-err {e}")
            if self._force_reconnect:
                break

    def run(self) -> int:
        info(f"INFO airc-console machine={self.machine} channel={self.channel} nick={self.nick}")
        if not self.server_password:
            info(
                "ERROR no-server-pass: set ConsoleHome/ergo.password or AGENTIC_IRC_PASSWORD. "
                "irc.ntsa.uk requires PASS; without it TLS ends EOF and the console never registers."
            )
            return 2
        backoff = RECONNECT_MIN_S
        while not self._stop.is_set():
            session_ok = False
            try:
                self.connect()
                self.handshake()
                self.read_loop()
                session_ok = self._registered
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
            if session_ok:
                backoff = RECONNECT_MIN_S
            info(f"INFO reconnect in {backoff:.0f}s (registered={session_ok})")
            time.sleep(backoff)
            backoff = min(RECONNECT_MAX_S, max(RECONNECT_MIN_S, backoff * 2))
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
        help="IRC nick (default auto = {machine}_console handshake; FR #314 may NICK-change after ChanServ probe)",
    )
    p.add_argument(
        "--machine",
        default=None,
        help="fleet shop id (ionos/flamingo/…); default AIRC_CONSOLE_MACHINE / BOB_MACHINE_ID / COMPUTERNAME",
    )
    p.add_argument(
        "--domain",
        default=None,
        help="lobby channel id when shop not ChanServ-registered (FR #314); default AIRC_CONSOLE_DOMAIN / Windows domain|workgroup",
    )
    p.add_argument(
        "--channel",
        default=None,
        help="force JOIN channel (skips ChanServ probe); default auto shop/lobby",
    )
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
    assert console_nick("IONOS") == "ionos_console"
    assert console_nick("IONOS", "auto") == "ionos_console"
    assert console_nick("IONOS", "console") == "console"
    assert shop_console_nick("flamingo") == "flamingo_console"
    assert lobby_nick("flamingo", 0) == "flamingo"
    assert lobby_nick("flamingo", 2) == "flamingo_2"
    assert domain_id("WONDERLAND.LOCAL") == "wonderland-local"
    assert parse_chanserv_registered("Channel #ionos is not registered.") is False
    assert parse_chanserv_registered("Channel #ionos is registered.") is True
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
