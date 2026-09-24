"""Watch-AgentHealth helpers (issue #135 / #144): IRC TSR probe + session store.

Caller polls listen sinks for ^FROM lines; the agent still owns irc_agent.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from talk_seat_pid import parse_coordinator_pid

try:
    import irc_listen
except ImportError:  # pragma: no cover - scripts/ on path in tests
    irc_listen = None  # type: ignore[assignment]

DEFAULT_IRC_STALE_SECONDS = 900
_FROM_LINE = re.compile(r"^FROM\s", re.MULTILINE)
ListenSinkKind = Literal["stdout", "tsr", "irc_log"]

BOOT_SKILL_MARKERS = (
    "Load irc + build skills",
    "CAST IRON harvest",
)

CURSOR_SESSION_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def session_store_path(engine: str, profile: Path | None = None) -> Path:
    """On-disk session id for Watch-AgentHealth (--cursor / --grok / --aider)."""
    root = profile or Path.home()
    eng = (engine or "").strip().lower()
    if eng not in ("cursor", "grok", "aider"):
        raise ValueError("engine must be cursor, grok, or aider")
    return root / ".grok" / "bob-bridge" / f"watch-agent-health-{eng}.session"


def read_session_id(path: Path | str) -> str | None:
    p = Path(path)
    if not p.is_file():
        return None
    try:
        raw = p.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return raw or None


def write_session_id(path: Path | str, session_id: str) -> None:
    sid = (session_id or "").strip()
    if not sid:
        return
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(sid + "\n", encoding="utf-8", newline="\n")


def cursor_session_bound_marker(path: Path | str) -> Path:
    p = Path(path)
    return p.with_suffix(p.suffix + ".bound")


def write_cursor_bound_session(path: Path | str, session_id: str) -> None:
    """Persist session_id only after Cursor CLI returned it (not a pre-boot GUID)."""
    write_session_id(path, session_id)
    marker = cursor_session_bound_marker(path)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("cursor-cli-json\n", encoding="utf-8", newline="\n")


def is_bound_cursor_session_id(session_id: str | None, session_path: Path | str | None = None) -> bool:
    """True when Cursor session was bound from CLI output (marker + plausible id)."""
    if not session_id or not CURSOR_SESSION_ID_RE.match(session_id.strip()):
        return False
    if session_path is None:
        return False
    return cursor_session_bound_marker(session_path).is_file()


def parse_cursor_session_id(cli_output: str) -> str | None:
    """Extract session_id from cursor-agent --print --output-format json stdout."""
    for line in (cli_output or "").splitlines():
        text = line.strip()
        if not text.startswith("{"):
            continue
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            continue
        sid = obj.get("session_id")
        if isinstance(sid, str) and sid.strip():
            return sid.strip()
    return None


def wake_prompt_includes_boot_skills(text: str) -> bool:
    return any(marker in (text or "") for marker in BOOT_SKILL_MARKERS)


def filter_from_lines(text: str) -> list[str]:
    if not text:
        return []
    return [ln for ln in text.splitlines() if ln.startswith("FROM ")]


def listen_sink_candidates(irc_home: Path | str) -> list[tuple[ListenSinkKind, Path]]:
    home = Path(irc_home)
    return [
        ("stdout", home / "listen.stdout.log"),
        ("tsr", home / "listen-tsr.log"),
        ("irc_log", home / "irc.log"),
    ]


def _probe_log_path(path: Path) -> tuple[bool, bool, datetime | None]:
    """Return (exists, readable, mtime_utc)."""
    if not path.is_file():
        return False, False, None
    try:
        with path.open("rb"):
            pass
    except OSError:
        return True, False, None
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    except OSError:
        return True, False, None
    return True, True, mtime


def select_listen_poll_sink(irc_home: Path | str) -> tuple[Path, ListenSinkKind]:
    """Pick the listen log health/forward should poll (not stdout-only)."""
    readable: list[tuple[ListenSinkKind, Path, datetime]] = []
    for kind, path in listen_sink_candidates(irc_home):
        exists, ok, mtime = _probe_log_path(path)
        if exists and ok and mtime is not None:
            readable.append((kind, path, mtime))
    if not readable:
        home = Path(irc_home)
        return home / "listen.stdout.log", "stdout"
    kind, path, _ = max(readable, key=lambda item: item[2])
    return path, kind


def listen_health_sink(
    irc_home: Path | str,
    stale_seconds: int = DEFAULT_IRC_STALE_SECONDS,
    now_utc: datetime | None = None,
) -> tuple[bool, bool, datetime | None, Path | None]:
    """log_exists, log_stale, mtime, chosen_path — uses best readable sink."""
    now = now_utc or datetime.now(timezone.utc)
    readable: list[tuple[Path, datetime]] = []
    for _kind, path in listen_sink_candidates(irc_home):
        exists, ok, mtime = _probe_log_path(path)
        if exists and ok and mtime is not None:
            readable.append((path, mtime))
    if not readable:
        return False, False, None, None
    path, mtime = max(readable, key=lambda item: item[1])
    age = (now - mtime).total_seconds()
    stale = age > stale_seconds
    return True, stale, mtime, path


def _from_lines_from_irc_log_chunk(chunk: str) -> list[str]:
    if irc_listen is None:
        return []
    out: list[str] = []
    for raw in chunk.splitlines():
        line = irc_listen.format_talk_line(raw)
        if line:
            out.append(line)
    return out


def read_new_from_lines(
    log_path: Path | str,
    offset: int,
    *,
    sink_kind: ListenSinkKind = "stdout",
) -> tuple[list[str], int]:
    """Return (FROM lines since offset, new offset)."""
    p = Path(log_path)
    if not p.is_file():
        return [], offset
    try:
        data = p.read_bytes()
    except OSError:
        return [], offset
    if offset > len(data):
        offset = 0
    chunk = data[offset:].decode("utf-8", errors="replace")
    new_off = len(data)
    if sink_kind == "irc_log":
        return _from_lines_from_irc_log_chunk(chunk), new_off
    return filter_from_lines(chunk), new_off


def commit_listen_offset_after_wake(
    *,
    agent_started: bool,
    exit_code: int | None,
    current_offset: int,
    next_offset: int,
) -> int:
    """Advance offset only after a successful Agent TSR delivery."""
    if not agent_started:
        return current_offset
    if exit_code != 0:
        return current_offset
    return next_offset


@dataclass(frozen=True)
class IrcTsrStatus:
    agent_pid: int
    listen_pid: int
    nick: str
    agent_alive: bool
    listen_alive: bool
    log_exists: bool
    log_stale: bool
    listen_log_path: Path | None = None

    @property
    def healthy(self) -> bool:
        return (
            self.agent_alive
            and self.listen_alive
            and self.log_exists
            and not self.log_stale
        )


def coordinator_pids(coord_text: str) -> tuple[int, int, str]:
    doc = parse_coordinator_pid(coord_text)
    nick = (doc.get("nick") or "").strip()

    def _int(key: str) -> int:
        raw = (doc.get(key) or "").strip()
        try:
            return int(raw)
        except ValueError:
            return 0

    return _int("agent"), _int("listen"), nick


def evaluate_irc_tsr(
    *,
    agent_pid: int,
    listen_pid: int,
    nick: str,
    agent_alive: bool,
    listen_alive: bool,
    log_exists: bool,
    log_mtime_utc: datetime | None,
    stale_seconds: int = DEFAULT_IRC_STALE_SECONDS,
    now_utc: datetime | None = None,
    listen_log_path: Path | None = None,
) -> IrcTsrStatus:
    now = now_utc or datetime.now(timezone.utc)
    stale = False
    if log_exists and log_mtime_utc is not None:
        age = (now - log_mtime_utc).total_seconds()
        if age > stale_seconds:
            stale = True
    elif not log_exists:
        stale = False
    return IrcTsrStatus(
        agent_pid=agent_pid,
        listen_pid=listen_pid,
        nick=nick,
        agent_alive=agent_alive,
        listen_alive=listen_alive,
        log_exists=log_exists,
        log_stale=stale,
        listen_log_path=listen_log_path,
    )


def format_irc_wake_payload(from_lines: list[str], sink_name: str = "listen log") -> str:
    body = "\n".join(from_lines)
    return (
        f"IRC wake (caller polled {sink_name}; you were triggered because data exists):\n\n"
        f"{body}\n\n"
        "Act on #bobiverse traffic. Harvest skills if you learn a playbook. No UAT."
    )


def format_aider_wake_payload(from_lines: list[str], sink_name: str = "listen log") -> str:
    """Compact wake for a live aider.exe REPL (SendKeys / WriteConsoleInput — not --message)."""
    body = "\n".join(from_lines)
    return (
        f"IRC wake ({sink_name}):\n{body}\n"
        "Act on addressed IRC traffic (pong on ping). Prefer outbox replies. No UAT. "
        "Do not exit the REPL."
    )


def cursor_boot_required(session_path: Path | str) -> bool:
    sid = read_session_id(session_path)
    return not is_bound_cursor_session_id(sid, session_path)


def cursor_wake_argv_includes_resume(session_path: Path | str) -> bool:
    sid = read_session_id(session_path)
    return is_bound_cursor_session_id(sid, session_path)
