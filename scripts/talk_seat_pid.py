"""Talk-seat identity: IRC nick {machine-id}-{agentPid} uses irc_agent PID only."""
from __future__ import annotations

import re
from pathlib import Path

from bobreport import FLEET_MACHINE_IDS, normalize_machine_id

_COORD_LINE = re.compile(r"^([a-z_]+)=(.*)$", re.IGNORECASE)


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


def validate_nick_agent_pid(nick: str, agent_pid: int | str) -> bool:
    suffix = nick_suffix_pid(nick)
    if suffix is None:
        return True
    try:
        return int(suffix) == int(agent_pid)
    except (TypeError, ValueError):
        return False


def check_nick_agent_pid(nick: str, agent_pid: int | str) -> str | None:
    """None if OK; else human-readable INFO line (no newline)."""
    suffix = nick_suffix_pid(nick)
    if suffix is None:
        return None
    try:
        want = int(agent_pid)
        have = int(suffix)
    except (TypeError, ValueError):
        return "INFO talk-seat nick suffix is not a valid pid"
    if have != want:
        return (
            f"INFO talk-seat nick suffix {have} != irc_agent PID {want} "
            "(use agent PID, not irc_listen PID)"
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


def coordinator_agent_pid(home: Path | str) -> int | None:
    path = Path(home) / "coordinator.pid"
    if not path.is_file():
        return None
    try:
        doc = parse_coordinator_pid(path.read_text(encoding="utf-8"))
    except OSError:
        return None
    raw = (doc.get("agent") or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def check_coordinator_nick(home: Path | str) -> str | None:
    """Validate coordinator.pid nick suffix matches authoritative agent= line."""
    path = Path(home) / "coordinator.pid"
    if not path.is_file():
        return None
    try:
        doc = parse_coordinator_pid(path.read_text(encoding="utf-8"))
    except OSError:
        return None
    nick = (doc.get("nick") or "").strip()
    agent_raw = (doc.get("agent") or "").strip()
    if not nick or not agent_raw:
        return None
    try:
        agent_pid = int(agent_raw)
    except ValueError:
        return "INFO coordinator.pid agent= is not a valid pid"
    return check_nick_agent_pid(nick, agent_pid)


def auto_talk_seat_nick(nick: str, agent_pid: int) -> str:
    """If nick is a talk-seat for a machine, rewrite suffix to agent_pid."""
    parsed = parse_talk_seat_nick(nick)
    if not parsed:
        return nick
    mid, _ = parsed
    return talk_seat_nick(mid, agent_pid)


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    p = argparse.ArgumentParser(description="Talk-seat nick / coordinator.pid guard")
    p.add_argument("--home", default="", help="check coordinator.pid under this home")
    p.add_argument("--nick", default="")
    p.add_argument("--pid", type=int, default=0)
    args = p.parse_args(argv)
    if args.home:
        err = check_coordinator_nick(args.home)
    elif args.nick and args.pid:
        err = check_nick_agent_pid(args.nick, args.pid)
    else:
        print("INFO pass --home or --nick and --pid", flush=True)
        return 1
    if err:
        print(err, flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
