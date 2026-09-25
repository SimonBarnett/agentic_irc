"""FR #213: exponential restart backoff for monitors that re-spawn irc_agent.

A crash loop that relaunches every few seconds trips Ergo's per-IP connect
throttle. Track consecutive *fast* exits and sleep with growth + hard cap
before the next repair/start.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path

# Defaults: base 2s, double each fast exit, cap 300s (5 min). Fast = exited
# within FAST_EXIT_S of start (crash / nick-guard fail loop was ~17s).
DEFAULT_BASE_S = 2.0
DEFAULT_CAP_S = 300.0
DEFAULT_FAST_EXIT_S = 45.0
STATE_NAME = "monitor-restart-backoff.json"


@dataclass
class BackoffState:
    consecutive_fast: int = 0
    last_start_unix: float = 0.0
    last_exit_unix: float = 0.0
    last_delay_s: float = 0.0


def _env_float(name: str, default: float) -> float:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        v = float(raw)
    except ValueError:
        return default
    return v if v > 0 else default


def base_s() -> float:
    return _env_float("AGENTIC_IRC_MONITOR_BACKOFF_BASE_S", DEFAULT_BASE_S)


def cap_s() -> float:
    return _env_float("AGENTIC_IRC_MONITOR_BACKOFF_CAP_S", DEFAULT_CAP_S)


def fast_exit_s() -> float:
    return _env_float("AGENTIC_IRC_MONITOR_FAST_EXIT_S", DEFAULT_FAST_EXIT_S)


def delay_after_fast_exits(n: int, *, base: float | None = None, cap: float | None = None) -> float:
    """Seconds to wait before next restart after n consecutive fast exits (n>=1)."""
    b = float(base if base is not None else base_s())
    c = float(cap if cap is not None else cap_s())
    if n <= 0:
        return 0.0
    # n=1 → base, n=2 → 2*base, ...
    delay = b * (2 ** (n - 1))
    return float(min(c, delay))


def state_path(home: Path | str) -> Path:
    return Path(home) / STATE_NAME


def load_state(home: Path | str) -> BackoffState:
    p = state_path(home)
    if not p.is_file():
        return BackoffState()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return BackoffState()
    if not isinstance(raw, dict):
        return BackoffState()
    try:
        return BackoffState(
            consecutive_fast=int(raw.get("consecutive_fast") or 0),
            last_start_unix=float(raw.get("last_start_unix") or 0),
            last_exit_unix=float(raw.get("last_exit_unix") or 0),
            last_delay_s=float(raw.get("last_delay_s") or 0),
        )
    except (TypeError, ValueError):
        return BackoffState()


def save_state(home: Path | str, state: BackoffState) -> None:
    p = state_path(home)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(state), indent=2) + "\n", encoding="utf-8", newline="\n")


def note_start(home: Path | str, *, now: float | None = None) -> BackoffState:
    st = load_state(home)
    st.last_start_unix = float(now if now is not None else time.time())
    save_state(home, st)
    return st


def note_exit(
    home: Path | str,
    *,
    now: float | None = None,
    fast_window_s: float | None = None,
) -> tuple[BackoffState, float]:
    """Record an exit; return (state, delay_s to wait before next start)."""
    st = load_state(home)
    t = float(now if now is not None else time.time())
    st.last_exit_unix = t
    window = float(fast_window_s if fast_window_s is not None else fast_exit_s())
    started = st.last_start_unix
    if started > 0 and (t - started) <= window:
        st.consecutive_fast += 1
    else:
        st.consecutive_fast = 0
    delay = delay_after_fast_exits(st.consecutive_fast)
    st.last_delay_s = delay
    save_state(home, st)
    return st, delay


def note_healthy(home: Path | str) -> BackoffState:
    """Healthy IRC session: clear consecutive fast counter."""
    st = load_state(home)
    st.consecutive_fast = 0
    st.last_delay_s = 0.0
    save_state(home, st)
    return st


def sleep_before_repair(home: Path | str, *, sleep_fn=None) -> float:
    """If prior exit was fast, sleep the computed delay. Returns seconds slept."""
    st = load_state(home)
    delay = float(st.last_delay_s or 0.0)
    if delay <= 0:
        return 0.0
    (sleep_fn or time.sleep)(delay)
    return delay


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="FR #213 monitor restart backoff")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_d = sub.add_parser("delay")
    p_d.add_argument("--n", type=int, required=True)

    p_s = sub.add_parser("note-start")
    p_s.add_argument("--home", required=True)

    p_e = sub.add_parser("note-exit")
    p_e.add_argument("--home", required=True)

    p_h = sub.add_parser("note-healthy")
    p_h.add_argument("--home", required=True)

    p_w = sub.add_parser("wait")
    p_w.add_argument("--home", required=True)

    args = p.parse_args(argv)
    if args.cmd == "delay":
        print(f"{delay_after_fast_exits(args.n):.3f}")
        return 0
    if args.cmd == "note-start":
        st = note_start(args.home)
        print(json.dumps(asdict(st)))
        return 0
    if args.cmd == "note-exit":
        st, delay = note_exit(args.home)
        print(json.dumps({**asdict(st), "delay_s": delay}))
        return 0
    if args.cmd == "note-healthy":
        st = note_healthy(args.home)
        print(json.dumps(asdict(st)))
        return 0
    if args.cmd == "wait":
        slept = sleep_before_repair(args.home)
        print(f"{slept:.3f}")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
