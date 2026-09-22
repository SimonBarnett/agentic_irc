"""Watch-AgentHealth helpers (issue #135): IRC TSR probe + session store paths.

Caller polls listen.stdout.log for ^FROM lines; the agent still owns irc_agent.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from talk_seat_pid import parse_coordinator_pid

DEFAULT_IRC_STALE_SECONDS = 900
_FROM_LINE = re.compile(r"^FROM\s", re.MULTILINE)


def session_store_path(engine: str, profile: Path | None = None) -> Path:
    """On-disk session id for Watch-AgentHealth (--cursor / --grok)."""
    root = profile or Path.home()
    eng = (engine or "").strip().lower()
    if eng not in ("cursor", "grok"):
        raise ValueError("engine must be cursor or grok")
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


def filter_from_lines(text: str) -> list[str]:
    if not text:
        return []
    return [ln for ln in text.splitlines() if ln.startswith("FROM ")]


def read_new_from_lines(
    log_path: Path | str,
    offset: int,
) -> tuple[list[str], int]:
    """Return (FROM lines since offset, new offset)."""
    p = Path(log_path)
    if not p.is_file():
        return [], offset
    data = p.read_bytes()
    if offset > len(data):
        offset = 0
    chunk = data[offset:].decode("utf-8", errors="replace")
    new_off = len(data)
    return filter_from_lines(chunk), new_off


@dataclass(frozen=True)
class IrcTsrStatus:
    agent_pid: int
    listen_pid: int
    nick: str
    agent_alive: bool
    listen_alive: bool
    log_exists: bool
    log_stale: bool

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
    )


def format_irc_wake_payload(from_lines: list[str]) -> str:
    body = "\n".join(from_lines)
    return (
        "IRC wake (caller polled listen.stdout.log; you were triggered because data exists):\n\n"
        f"{body}\n\n"
        "Act on #bobiverse traffic. Harvest skills if you learn a playbook. No UAT."
    )
