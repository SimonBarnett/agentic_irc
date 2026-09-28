#!/usr/bin/env python3
"""airc console service core (FR #253).

Installable Windows service presence nick ``console`` on ``#{machinename}``.
Silent in channel. Authenticated PRIVMSG sessions get a per-user console pipe.

Offline-testable: auth, channel naming, session lifecycle, silent policy.
Live IRC loop lives in ``airc_console_service.py``.
"""
from __future__ import annotations

import fnmatch
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
_CTCP_PING_RE = re.compile(r"^\x01PING(?: (.*))?\x01\s*$", re.IGNORECASE | re.DOTALL)
_PING_CMD_RE = re.compile(r"^\s*ping(?:\s+(\S+))?\s*$", re.IGNORECASE)
# Issue #302: fleet ear nicks bob-{machine} are already authenticated; machine varies.
_BOB_FLEET_NICK_RE = re.compile(r"^bob-[a-z0-9][a-z0-9_-]*$", re.IGNORECASE)


def machine_id(override: str | None = None) -> str:
    """Fleet shop id for ``#{machine}`` / ``console-<machine>``.

    Prefer explicit override, then ``AIRC_CONSOLE_MACHINE`` / ``BOB_MACHINE_ID``
    (fleet ids like ``ionos``), then Windows ``COMPUTERNAME``. Using bare
    COMPUTERNAME alone (e.g. ``WIN-MPRE8VI4U6U``) joins the wrong channel and
    looks like \"does not connect\" on ``#ionos`` / ``#flamingo``.
    """
    raw = (
        override
        or os.environ.get("AIRC_CONSOLE_MACHINE")
        or os.environ.get("BOB_MACHINE_ID")
        or os.environ.get("COMPUTERNAME")
        or os.environ.get("HOSTNAME")
        or "unknown"
    ).strip()
    cleaned = _CHANNEL_SAFE.sub("-", raw).strip("-_")
    return (cleaned or "unknown").lower()


def shop_channel(machine: str | None = None) -> str:
    mid = machine_id(machine)
    return f"#{mid}"


def console_nick(machine: str | None = None, explicit: str | None = None) -> str:
    """IRC nick for the console seat (issue #286).

    Bare ``console`` collides on a shared Ergo (433) when more than one box
    runs airc-console. Default is ``console-<machine>`` (unique per box).
    Pass explicit ``console`` only on a single-console network.
    """
    if explicit and explicit.strip() and explicit.strip().lower() != "auto":
        return explicit.strip()
    mid = machine_id(machine)
    nick = f"console-{mid}"
    return nick[:30]


def is_channel_target(target: str) -> bool:
    t = (target or "").strip()
    return bool(t) and t[0] in "#&+"


def nick_matches_pattern(pattern: str, nick: str, machine: str | None = None) -> bool:
    """True if IRC/client ping pattern matches this console (#298).

    Examples: ``*``, ``flam*``, ``console-flam*``, ``flamingo``, ``console-flamingo``.
    """
    pat = (pattern or "").strip()
    if not pat or pat == "*":
        return True
    n = (nick or "").strip().lower()
    mid = machine_id(machine)
    candidates = {n, mid, f"console-{mid}", f"#{mid}"}
    p = pat.lower()
    # Allow #channel-style patterns too.
    for c in candidates:
        if not c:
            continue
        if fnmatch.fnmatchcase(c, p) or fnmatch.fnmatchcase(c.lstrip("#"), p.lstrip("#")):
            return True
        # Prefix match without wildcard: "flam" matches flamingo / console-flamingo
        if "*" not in p and "?" not in p and (c.startswith(p) or c.lstrip("#").startswith(p)):
            return True
    return False


def parse_ctcp_ping(text: str) -> str | None:
    """Return CTCP PING payload (possibly empty string) or None if not CTCP PING."""
    m = _CTCP_PING_RE.match(text or "")
    if not m:
        return None
    return m.group(1) if m.group(1) is not None else ""


def parse_ping_command(text: str) -> str | None:
    """Return ping pattern (``*`` if bare ``ping``) or None if not a ping command."""
    m = _PING_CMD_RE.match(text or "")
    if not m:
        return None
    return (m.group(1) or "*").strip()


def is_bob_fleet_nick(nick: str) -> bool:
    """True for fleet ear nicks ``bob-{machinename}`` (issue #302)."""
    return bool(_BOB_FLEET_NICK_RE.match((nick or "").strip()))


@dataclass
class AuthPolicy:
    """Only authenticated operators may drive the console via PRIVMSG."""

    operators: set[str] = field(default_factory=set)
    accounts: set[str] = field(default_factory=set)
    account_map: AccountMap | None = None
    require_account: bool = False
    # When set, also allow bob-<machine> for this box; bob-* fleet nicks always allowed (#302).
    machine: str | None = None

    def allow(self, nick: str, account: str | None = None) -> bool:
        n = (nick or "").strip().lower()
        if not n:
            return False
        # Fleet bob-{machine} seats are already authenticated on Ergo (#302).
        if is_bob_fleet_nick(n):
            return True
        ops = {x.lower() for x in self.operators}
        mid = machine_id(self.machine) if self.machine is not None else None
        if mid:
            ops.add(f"bob-{mid}")
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

        # Issue #298: CTCP PING / "ping [pattern]" — no operator auth; presence only.
        ctcp_payload = parse_ctcp_ping(text or "")
        if ctcp_payload is not None:
            return HandleResult(
                action="ctcp_pong",
                nick=nick,
                target=target,
                text=text,
                reply=ctcp_payload,
            )
        ping_pat = parse_ping_command(text or "")
        if ping_pat is not None:
            if nick_matches_pattern(ping_pat, self.nick, self.machine):
                return HandleResult(
                    action="pong",
                    nick=nick,
                    target=target,
                    text=text,
                    reply=f"pong {self.nick}",
                )
            if is_channel_target(target):
                self.channel_traffic.append(text)
                return HandleResult(action="silent_channel", nick=nick, target=target, text=text)
            # Direct ping that does not match us — ignore quietly.
            return HandleResult(action="ping_miss", nick=nick, target=target, text=text)

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
                reply="airc console: PRIVMSG lines pipe to your shell; .quit closes; silent on channel; answers ping",
            )

        self.sessions.pipe(nick, cmd)
        return HandleResult(action="pipe", nick=nick, target=target, text=text)


def load_operators(path: Path | None, cli: list[str] | None = None) -> set[str]:
    ops: set[str] = set()
    if cli:
        ops.update(x.strip().lstrip("\ufeff") for x in cli if x and x.strip())
    if path and path.is_file():
        # utf-8-sig strips BOM from PowerShell Set-Content -Encoding utf8 (issue #289).
        text = path.read_text(encoding="utf-8-sig")
        for line in text.splitlines():
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


def ensure_nickserv_password(path: Path, *, mint: bool = True) -> str | None:
    """Load or mint the NickServ password (issue #271).

    First start writes a GUID into ``console.password`` and reuses it later.
    This is **not** the Ergo server PASS — that comes from env / ergo.password.
    """
    import uuid

    if path.is_file():
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    if not mint:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    secret = str(uuid.uuid4())
    path.write_text(secret + "\n", encoding="utf-8")
    try:
        # Best-effort: owner-only on POSIX; Windows ACLs set by install/hotpatch.
        os.chmod(path, 0o600)
    except OSError:
        pass
    return secret


def resolve_server_password(
    *,
    home: Path | None = None,
    password_file: Path | None = None,
) -> str | None:
    """Ergo / IRC server PASS — never invent; never use NickServ GUID file alone.

    Order: AIRC_CONSOLE_SERVER_PASSWORD, AGENTIC_IRC_PASSWORD, AIRC_CONSOLE_PASSWORD
    (legacy), then ``ergo.password`` / ``connect.password`` beside home or
    ``~/.grok/ergo/connect.password``. Explicit ``password_file`` is **not** used
    here when it is the NickServ GUID path (``console.password``).
    """
    for key in (
        "AIRC_CONSOLE_SERVER_PASSWORD",
        "AGENTIC_IRC_PASSWORD",
        "AIRC_CONSOLE_PASSWORD",
    ):
        env = os.environ.get(key)
        if env and env.strip():
            return env.strip()
    candidates: list[Path] = []
    # Legacy: only treat password_file as server PASS when it is NOT console.password
    if password_file is not None and password_file.name.lower() != "console.password":
        candidates.append(password_file)
    if home is not None:
        candidates.extend(
            [
                home / "ergo.password",
                home / "connect.password",
            ]
        )
    # Fleet default connect.password — only when using the real user console home
    # (avoid leaking ~/.grok secrets into hermetic tests with a tmp home).
    real_home = home_dir()
    if home is None or Path(home).resolve() == real_home.resolve():
        candidates.append(Path.home() / ".grok" / "ergo" / "connect.password")
    for p in candidates:
        try:
            if p.is_file():
                text = p.read_text(encoding="utf-8").strip()
                if text:
                    return text
        except OSError:
            continue
    return None
