"""Talk-seat identity: IRC nick {machine-id}-{seatPid} uses coordinator PowerShell PID."""
from __future__ import annotations

import os
import re
from pathlib import Path

from bobreport import FLEET_MACHINE_IDS, normalize_machine_id

_COORD_LINE = re.compile(r"^([a-z_]+)=(.*)$", re.IGNORECASE)
_SEAT_ENV = "AGENTIC_IRC_SEAT_PID"


def parse_talk_seat_nick(nick: str) -> tuple[str, str] | None:
    """Return (machine_id, pid_str) for fleet talk-seat nicks, else None."""
    n = (nick or "").strip().lower()
    if not n or n.startswith("bob-") or n.startswith("w-"):
        return None
    for mid in sorted(FLEET_MACHINE_IDS, key=len, reverse=True):
        prefix = f"{mid}-"
        if not n.startswith(prefix):
            continue
        pid_s = n[len(prefix) :]
        if pid_s.isdigit() and int(pid_s) > 0:
            norm = normalize_machine_id(mid)
            if norm:
                return norm, pid_s
    return None


def talk_seat_nick(machine_id: str, pid: int | str) -> str:
    mid = normalize_machine_id(machine_id)
    if not mid:
        raise ValueError("bad machine id")
    return f"{mid}-{int(pid)}"


def nick_suffix_pid(nick: str) -> str | None:
    parsed = parse_talk_seat_nick(nick)
    return parsed[1] if parsed else None


def validate_nick_seat_pid(nick: str, seat_pid: int | str) -> bool:
    suffix = nick_suffix_pid(nick)
    if suffix is None:
        return True
    try:
        return int(suffix) == int(seat_pid)
    except (TypeError, ValueError):
        return False


def check_nick_seat_pid(nick: str, seat_pid: int | str) -> str | None:
    """None if OK; else human-readable INFO line (no newline)."""
    suffix = nick_suffix_pid(nick)
    if suffix is None:
        return None
    try:
        want = int(seat_pid)
        have = int(suffix)
    except (TypeError, ValueError):
        return "INFO talk-seat nick suffix is not a valid pid"
    if have != want:
        return (
            f"INFO talk-seat nick suffix {have} != seat PowerShell PID {want} "
            "(not python irc_listen or irc_agent PID)"
        )
    return None


def parse_coordinator_pid(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _COORD_LINE.match(line)
        if m:
            out[m.group(1).lower()] = m.group(2).strip()
    return out


def _seat_pid_from_doc(doc: dict[str, str]) -> int | None:
    raw = (doc.get("seat") or doc.get("host") or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def coordinator_seat_pid(home: Path | str) -> int | None:
    path = Path(home) / "coordinator.pid"
    if not path.is_file():
        return None
    try:
        doc = parse_coordinator_pid(path.read_text(encoding="utf-8"))
    except OSError:
        return None
    return _seat_pid_from_doc(doc)


def seat_pid_from_env() -> int | None:
    raw = (os.environ.get(_SEAT_ENV) or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def resolve_seat_pid(home: Path | str | None = None) -> int | None:
    """Coordinator PowerShell PID: env AGENTIC_IRC_SEAT_PID, then coordinator.pid seat=."""
    pid = seat_pid_from_env()
    if pid is not None:
        return pid
    if home:
        return coordinator_seat_pid(home)
    return None


def check_coordinator_nick(home: Path | str) -> str | None:
    """Validate coordinator.pid nick suffix matches authoritative seat= line."""
    path = Path(home) / "coordinator.pid"
    if not path.is_file():
        return None
    try:
        doc = parse_coordinator_pid(path.read_text(encoding="utf-8"))
    except OSError:
        return None
    nick = (doc.get("nick") or "").strip()
    seat = _seat_pid_from_doc(doc)
    if not nick or seat is None:
        return None
    return check_nick_seat_pid(nick, seat)


def auto_talk_seat_nick(nick: str, seat_pid: int) -> str:
    """If nick is a talk-seat for a machine, rewrite suffix to seat_pid."""
    parsed = parse_talk_seat_nick(nick)
    if not parsed:
        return nick
    mid, _ = parsed
    return talk_seat_nick(mid, seat_pid)


def home_bind_refusal(
    coord: dict[str, str],
    expected_nick: str,
    *,
    live_agent_nick: str | None = None,
    has_live_listen: bool = False,
) -> str | None:
    """None if Start-TalkSeat may bind; else a one-line refusal (no secrets)."""
    expected = (expected_nick or "").strip()
    if not expected:
        return "expected talk-seat nick is required"
    lock_nick = (coord.get("nick") or "").strip()
    lock_seat = (coord.get("seat") or "").strip()
    agent_nick = (live_agent_nick or "").strip()
    occupied = bool(agent_nick) or has_live_listen

    if agent_nick and agent_nick != expected:
        if lock_nick == expected:
            return None
        seat_part = f" seat={lock_seat}" if lock_seat else ""
        return (
            f"home has live irc_agent nick={agent_nick}{seat_part}; "
            f"this seat wants {expected}. Use a different -IrcHome "
            "(e.g. ~/.agentic-irc-cursor-2). Do not kill the other seat's listen."
        )

    if lock_nick and lock_nick != expected and occupied:
        seat_part = f" seat={lock_seat}" if lock_seat else ""
        return (
            f"coordinator.pid nick={lock_nick}{seat_part} with live listen/agent; "
            f"this seat wants {expected}. Use a different -IrcHome "
            "(e.g. ~/.agentic-irc-cursor-2). Do not steal the first talk-seat home."
        )
    return None


def check_home_bind(
    home: Path | str,
    expected_nick: str,
    *,
    live_agent_nick: str | None = None,
    has_live_listen: bool = False,
) -> str | None:
    path = Path(home) / "coordinator.pid"
    doc: dict[str, str] = {}
    if path.is_file():
        try:
            doc = parse_coordinator_pid(path.read_text(encoding="utf-8"))
        except OSError:
            doc = {}
    return home_bind_refusal(
        doc,
        expected_nick,
        live_agent_nick=live_agent_nick,
        has_live_listen=has_live_listen,
    )


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    p = argparse.ArgumentParser(description="Talk-seat nick / coordinator.pid guard")
    p.add_argument("--home", default="", help="check coordinator.pid under this home")
    p.add_argument("--nick", default="")
    p.add_argument("--pid", type=int, default=0)
    p.add_argument(
        "--bind-home",
        action="store_true",
        help="refuse binding a home owned by another talk seat (exit 3)",
    )
    p.add_argument("--expected-nick", default="")
    p.add_argument("--live-agent-nick", default="")
    p.add_argument(
        "--live-listen",
        action="store_true",
        help="irc_listen is running for this home",
    )
    args = p.parse_args(argv)
    if args.bind_home:
        if not args.home or not args.expected_nick:
            print("INFO pass --home and --expected-nick with --bind-home", flush=True)
            return 1
        agent_nick = (args.live_agent_nick or "").strip() or None
        err = check_home_bind(
            args.home,
            args.expected_nick,
            live_agent_nick=agent_nick,
            has_live_listen=bool(args.live_listen),
        )
        if err:
            print(err, flush=True)
            return 3
        return 0
    if args.home:
        err = check_coordinator_nick(args.home)
    elif args.nick and args.pid:
        err = check_nick_seat_pid(args.nick, args.pid)
    else:
        print("INFO pass --home or --nick and --pid", flush=True)
        return 1
    if err:
        print(err, flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
