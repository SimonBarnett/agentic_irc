#!/usr/bin/env python3
"""FR #238: sanctioned detached irc_agent + irc_listen launcher (Windows).

Seat agents must **never** start IRC from a tool shell (children die with the
job). Prefer Watch-AgentHealth ``irc ensure``. When a one-shot launch is
needed (ops / recovery), use this script or ``Start-IrcPair.ps1``.

Windows creation flags (best-effort):
  CREATE_BREAKAWAY_FROM_JOB | CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS

``--coordinator-pid`` is written to ``coordinator.pid`` as ``seat=`` so
``irc_agent`` quits when that monitor/seat process dies (not when the
launcher exits).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

import prior_irc

SCRIPTS = Path(__file__).resolve().parent

# Win32 process creation flags
CREATE_NEW_PROCESS_GROUP = 0x00000200
DETACHED_PROCESS = 0x00000008
CREATE_BREAKAWAY_FROM_JOB = 0x01000000
CREATE_NO_WINDOW = 0x08000000


def _win_creationflags(*, breakaway: bool) -> int:
    flags = CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS | CREATE_NO_WINDOW
    if breakaway:
        flags |= CREATE_BREAKAWAY_FROM_JOB
    return flags


def _popen_detached(cmd: list[str], *, cwd: str, breakaway: bool) -> subprocess.Popen[bytes]:
    if sys.platform != "win32":
        return subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    flags = _win_creationflags(breakaway=breakaway)
    try:
        return subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=flags,
            close_fds=True,
        )
    except OSError:
        if not breakaway:
            raise
        # Job may disallow breakaway — fall back without CREATE_BREAKAWAY_FROM_JOB.
        return subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=_win_creationflags(breakaway=False),
            close_fds=True,
        )


def _find_python_on_home(home: Path, script_name: str) -> int | None:
    needle = script_name.replace("\\", "/").lower()
    home_s = str(home).replace("\\", "/").lower()
    if sys.platform != "win32":
        return None
    try:
        # Prefer CIM via powershell for reliability without psutil dependency.
        ps = (
            "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
            "ForEach-Object { '{0}|{1}' -f $_.ProcessId, $_.CommandLine }"
        )
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps],
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    for line in out.splitlines():
        if "|" not in line:
            continue
        pid_s, cl = line.split("|", 1)
        cl_l = (cl or "").replace("\\", "/").lower()
        if needle in cl_l and home_s in cl_l:
            try:
                return int(pid_s)
            except ValueError:
                continue
    return None


def write_coordinator_pid(
    home: Path,
    *,
    nick: str,
    coordinator_pid: int,
    agent_pid: int,
    listen_pid: int,
) -> Path:
    path = home / "coordinator.pid"
    lines = [
        f"nick={nick}",
        f"seat={int(coordinator_pid)}",
        f"listen={int(listen_pid)}",
        f"agent={int(agent_pid)}",
        f"home={home}",
        "launcher=start_irc_pair",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def start_pair(
    *,
    home: Path,
    nick: str,
    channel: str,
    coordinator_pid: int,
    host: str,
    port: str,
    python: str,
    breakaway: bool = True,
    dry_run: bool = False,
) -> dict[str, int | str]:
    home = home.expanduser().resolve()
    home.mkdir(parents=True, exist_ok=True)
    agent_py = SCRIPTS / "irc_agent.py"
    listen_py = SCRIPTS / "irc_listen.py"
    if not agent_py.is_file() or not listen_py.is_file():
        raise SystemExit(f"missing irc_agent/irc_listen under {SCRIPTS}")

    if coordinator_pid <= 0:
        raise SystemExit("--coordinator-pid must be a live seat/monitor PID (>0)")

    stdout_log = home / "listen.stdout.log"
    stderr_log = home / "listen.stderr.log"
    listen_cmd = [
        python,
        "-u",
        str(listen_py),
        "--home",
        str(home),
        "--stdout-log",
        str(stdout_log),
        "--stderr-log",
        str(stderr_log),
    ]
    agent_cmd = [
        python,
        "-u",
        str(agent_py),
        "--host",
        host,
        "--port",
        str(port),
        "--channel",
        channel,
        "--home",
        str(home),
        "--nick",
        nick,
    ]
    if dry_run:
        print("LISTEN", " ".join(listen_cmd))
        print("AGENT", " ".join(agent_cmd))
        print(f"coordinator_pid={coordinator_pid}")
        return {"listen": 0, "agent": 0, "seat": coordinator_pid, "nick": nick}

    cleaned = prior_irc.clean_priors(nick, str(home), self_pid=os.getpid())
    if not cleaned.scanned:
        raise SystemExit("prior-clean aborted pair start")

    # Ensure seat env so nick-suffix / liveness can prefer monitor PID.
    env = os.environ.copy()
    env["AGENTIC_IRC_COORDINATOR_PID"] = str(int(coordinator_pid))
    # Watch seats: nick suffix is monitor PID; keep SEAT_PID aligned for guards.
    env.setdefault("AGENTIC_IRC_SEAT_PID", str(int(coordinator_pid)))

    listen_proc = _popen_detached(listen_cmd, cwd=str(SCRIPTS), breakaway=breakaway)
    # Pass env to agent only (listen does not need coordinator env).
    if sys.platform == "win32":
        flags = _win_creationflags(breakaway=breakaway)
        try:
            agent_proc = subprocess.Popen(
                agent_cmd,
                cwd=str(SCRIPTS),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                creationflags=flags,
                close_fds=True,
                env=env,
            )
        except OSError:
            agent_proc = subprocess.Popen(
                agent_cmd,
                cwd=str(SCRIPTS),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                creationflags=_win_creationflags(breakaway=False),
                close_fds=True,
                env=env,
            )
    else:
        agent_proc = subprocess.Popen(
            agent_cmd,
            cwd=str(SCRIPTS),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
            env=env,
        )

    # Brief settle; re-resolve PIDs from CIM when Popen handles are unreliable after detach.
    time.sleep(0.4)
    listen_pid = int(listen_proc.pid or 0) or (_find_python_on_home(home, "irc_listen.py") or 0)
    agent_pid = int(agent_proc.pid or 0) or (_find_python_on_home(home, "irc_agent.py") or 0)
    if listen_pid <= 0 or agent_pid <= 0:
        raise SystemExit(f"failed to start pair listen={listen_pid} agent={agent_pid}")

    write_coordinator_pid(
        home,
        nick=nick,
        coordinator_pid=coordinator_pid,
        agent_pid=agent_pid,
        listen_pid=listen_pid,
    )
    print(
        f"started nick={nick} seat={coordinator_pid} agent={agent_pid} "
        f"listen={listen_pid} home={home} launcher=start_irc_pair"
    )
    return {
        "listen": listen_pid,
        "agent": agent_pid,
        "seat": coordinator_pid,
        "nick": nick,
        "home": str(home),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--coordinator-pid",
        type=int,
        required=True,
        help="Seat monitor / Watch-AgentHealth PID written as coordinator.pid seat=",
    )
    ap.add_argument("--home", required=True, help="IRC home (e.g. ~/.agentic-irc-watch-grok)")
    ap.add_argument("--nick", required=True, help="IRC nick (watch seats: {machine}-{monitorPid})")
    ap.add_argument(
        "--channel",
        default="",
        help="Comma channels; default #{machine} from nick when possible",
    )
    ap.add_argument("--host", default=os.environ.get("AGENTIC_IRC_HOST", "irc.ntsa.uk"))
    ap.add_argument("--port", default=os.environ.get("AGENTIC_IRC_PORT", "6697"))
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument(
        "--no-breakaway",
        action="store_true",
        help="Do not set CREATE_BREAKAWAY_FROM_JOB (DETACHED_PROCESS still used)",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    channel = (args.channel or "").strip()
    if not channel:
        # {machine}-{pid} → #{machine}
        parts = args.nick.rsplit("-", 1)
        if len(parts) == 2 and parts[1].isdigit():
            channel = f"#{parts[0].lower()}"
        else:
            raise SystemExit("--channel required when nick is not {machine}-{pid}")

    start_pair(
        home=Path(args.home),
        nick=args.nick.strip(),
        channel=channel,
        coordinator_pid=int(args.coordinator_pid),
        host=str(args.host),
        port=str(args.port),
        python=str(args.python),
        breakaway=not args.no_breakaway,
        dry_run=bool(args.dry_run),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
