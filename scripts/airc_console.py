#!/usr/bin/env python3
"""airc console service core (FR #253).

Installable Windows service presence nick ``console`` on ``#{machinename}``.
Silent in channel. Authenticated PRIVMSG sessions get a per-user console pipe.

Offline-testable: auth, channel naming, session lifecycle, silent policy.
Live IRC loop lives in ``airc_console_service.py``.
"""
from __future__ import annotations

import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from account_map import AccountMap, parse_message_tags

NICK = "console"
DEFAULT_SHELL = os.environ.get("COMSPEC") or "cmd.exe"
_PRIVMSG_RE = re.compile(
    r"^:([^!\s]+)(?:![^@\s]*@\S+)?\s+PRIVMSG\s+(\S+)\s+:?(.*)$",
    re.IGNORECASE,
)
_CHANNEL_SAFE = re.compile(r"[^A-Za-z0-9_-]+")


def machine_id(override: str | None = None) -> str:
    raw = (override or os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or "unknown").strip()
    cleaned = _CHANNEL_SAFE.sub("-", raw).strip("-_")
    return (cleaned or "unknown").lower()


def shop_channel(machine: str | None = None) -> str:
    mid = machine_id(machine)
    return f"#{mid}"


def is_channel_target(target: str) -> bool:
    t = (target or "").strip()
    return bool(t) and t[0] in "#&+"


@dataclass
class AuthPolicy:
    """Only authenticated operators may drive the console via PRIVMSG."""

    operators: set[str] = field(default_factory=set)
    accounts: set[str] = field(default_factory=set)
    account_map: AccountMap | None = None
    require_account: bool = False

    def allow(self, nick: str, account: str | None = None) -> bool:
        n = (nick or "").strip().lower()
        if not n:
            return False
        ops = {x.lower() for x in self.operators}
        accts = {x.lower() for x in self.accounts}
        if self.account_map is not None and account is None:
            account = self.account_map.get(n)
        acct = (account or "").strip().lower()
        need_acct = self.require_account or bool(accts)
        if need_acct:
            if not acct or acct == "*":
                return False
            if accts and acct not in accts:
                return False
        if ops:
            return n in ops
        return need_acct


@dataclass
class ConsoleSession:
    nick: str
    proc: subprocess.Popen[str]
    created_at: float = field(default_factory=time.time)
    last_at: float = field(default_factory=time.time)

    def write_line(self, text: str) -> None:
        self.last_at = time.time()
        if self.proc.stdin is None:
            raise RuntimeError("console stdin closed")
        self.proc.stdin.write(text + "\n")
        self.proc.stdin.flush()

    def alive(self) -> bool:
        return self.proc.poll() is None

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
        except Exception:
            pass
        try:
            if self.alive():
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=2)
                except Exception:
                    self.proc.kill()
        except Exception:
            pass


class ConsoleSessionManager:
    """One interactive shell per authenticated nick."""

    def __init__(
        self,
        *,
        shell: str | None = None,
        cwd: str | None = None,
        on_output: Callable[[str, str], None] | None = None,
        idle_sec: float = 3600.0,
    ) -> None:
        self.shell = shell or DEFAULT_SHELL
        self.cwd = cwd
        self.on_output = on_output
        self.idle_sec = idle_sec
        self._lock = threading.Lock()
        self._sessions: dict[str, ConsoleSession] = {}

    def get_or_create(self, nick: str) -> ConsoleSession:
        key = nick.strip().lower()
        with self._lock:
            sess = self._sessions.get(key)
            if sess and sess.alive():
                sess.last_at = time.time()
                return sess
            if sess:
                sess.close()
            proc = subprocess.Popen(
                [self.shell],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=self.cwd,
                bufsize=1,
            )
            sess = ConsoleSession(nick=key, proc=proc)
            self._sessions[key] = sess
            if self.on_output and proc.stdout is not None:
                threading.Thread(
                    target=self._pump,
                    args=(key, proc),
                    name=f"airc-console-{key}",
                    daemon=True,
                ).start()
            return sess

    def _pump(self, nick: str, proc: subprocess.Popen[str]) -> None:
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                text = line.rstrip("\r\n")
                if self.on_output:
                    self.on_output(nick, text)
        except Exception:
            pass

    def pipe(self, nick: str, command: str) -> ConsoleSession:
        sess = self.get_or_create(nick)
        sess.write_line(command)
        return sess

    def close_nick(self, nick: str) -> None:
        key = nick.strip().lower()
        with self._lock:
            sess = self._sessions.pop(key, None)
        if sess:
            sess.close()

    def close_all(self) -> None:
        with self._lock:
            items = list(self._sessions.items())
            self._sessions.clear()
        for _, sess in items:
            sess.close()

    def reap_idle(self, now: float | None = None) -> int:
        now = time.time() if now is None else now
        dead: list[str] = []
        with self._lock:
            for k, sess in list(self._sessions.items()):
                if (not sess.alive()) or (now - sess.last_at > self.idle_sec):
                    dead.append(k)
            for k in dead:
                sess = self._sessions.pop(k, None)
                if sess:
                    sess.close()
        return len(dead)

    def active(self) -> list[str]:
        with self._lock:
            return sorted(self._sessions.keys())


@dataclass
class HandleResult:
    action: str
    nick: str | None = None
    target: str | None = None
    text: str | None = None
    reply: str | None = None


class AircConsoleCore:
    """Pure handler: parse PRIVMSG, gate auth, pipe to console, stay silent on channel."""

    def __init__(
        self,
        *,
        machine: str | None = None,
        auth: AuthPolicy,
        sessions: ConsoleSessionManager | None = None,
        nick: str = NICK,
    ) -> None:
        self.machine = machine_id(machine)
        self.channel = shop_channel(self.machine)
        self.auth = auth
        self.nick = nick
        self.sessions = sessions or ConsoleSessionManager()
        self.channel_traffic: list[str] = []

    def register_commands(self) -> list[str]:
        """NickServ register / identify sequence (password from env/file at service layer)."""
        return [
            f"NICK {self.nick}",
            f"USER {self.nick} 0 * :airc console service",
        ]

    def join_commands(self) -> list[str]:
        # Ergo creates channel on first JOIN when permitted; silent — no PRIVMSG.
        return [f"JOIN {self.channel}"]

    def may_speak_on_channel(self) -> bool:
        return False

    def handle_raw(self, line: str) -> HandleResult | None:
        tags, rest = parse_message_tags(line.rstrip("\r\n"))
        m = _PRIVMSG_RE.match(rest)
        if not m:
            return None
        nick, target, text = m.group(1), m.group(2), m.group(3)
        account = tags.get("account")
        if self.auth.account_map is not None and account:
            self.auth.account_map.set(nick, account)

        if is_channel_target(target):
            # Silent in channel: ignore public traffic (do not reply on channel).
            self.channel_traffic.append(text)
            return HandleResult(action="silent_channel", nick=nick, target=target, text=text)

        # Direct PRIVMSG to console nick
        if not self.auth.allow(nick, account):
            return HandleResult(
                action="deny",
                nick=nick,
                target=target,
                text=text,
                reply="denied: authenticate / not an operator",
            )

        cmd = (text or "").strip()
        if not cmd:
            return HandleResult(action="empty", nick=nick, target=target, text=text)
        if cmd.lower() in {".quit", "!quit", "exit"}:
            self.sessions.close_nick(nick)
            return HandleResult(action="close", nick=nick, target=target, text=text, reply="console closed")
        if cmd.lower() in {".help", "!help"}:
            return HandleResult(
                action="help",
                nick=nick,
                target=target,
                text=text,
                reply="airc console: PRIVMSG lines pipe to your shell; .quit closes; silent on channel",
            )

        self.sessions.pipe(nick, cmd)
        return HandleResult(action="pipe", nick=nick, target=target, text=text)


def load_operators(path: Path | None, cli: list[str] | None = None) -> set[str]:
    ops: set[str] = set()
    if cli:
        ops.update(x.strip().lstrip("\ufeff") for x in cli if x and x.strip())
    if path and path.is_file():
        # Windows PowerShell 5.1 Set-Content -Encoding utf8 writes a BOM; strip it
        # so "Simon" matches nick simon (issue #259 follow-up / Halloy deny).
        raw = path.read_text(encoding="utf-8-sig")
        for line in raw.splitlines():
            s = line.strip().lstrip("\ufeff")
            if not s or s.startswith("#"):
                continue
            ops.add(s)
    return ops


def home_dir(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit)
    env = os.environ.get("AIRC_CONSOLE_HOME")
    if env:
        return Path(env)
    return Path.home() / ".airc-console"
