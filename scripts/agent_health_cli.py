"""CLI for agent_health."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from typing import Literal
from agent_health_core import (
    DEFAULT_IRC_STALE_SECONDS,
    ListenSinkKind,
    commit_listen_offset_after_wake,
    format_aider_wake_payload,
    format_irc_wake_payload,
    is_bound_cursor_session_id,
    listen_health_sink,
    parse_cursor_session_id,
    read_new_from_lines,
    read_session_id,
    select_listen_poll_sink,
    write_cursor_bound_session,
)

def _cli() -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(prog="agent_health.py")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_sink = sub.add_parser("select-sink")
    p_sink.add_argument("--home", required=True)

    p_health = sub.add_parser("listen-health")
    p_health.add_argument("--home", required=True)
    p_health.add_argument("--stale-seconds", type=int, default=DEFAULT_IRC_STALE_SECONDS)

    p_read = sub.add_parser("read-from")
    p_read.add_argument("--home", required=True)
    p_read.add_argument("--offset", type=int, default=0)
    p_read.add_argument("--sink-path", default="")
    p_read.add_argument("--sink-kind", default="")

    p_parse = sub.add_parser("parse-cursor-session")
    p_parse.add_argument("--file", required=True)

    p_bound = sub.add_parser("cursor-bound")
    p_bound.add_argument("--session-path", required=True)

    p_wake = sub.add_parser("format-wake")
    p_wake.add_argument("--sink-name", default="listen log")
    p_wake.add_argument("--lines", default="")
    p_wake.add_argument("--engine", default="", help="aider = compact live-REPL wake")

    p_mark = sub.add_parser("mark-cursor-bound")
    p_mark.add_argument("--session-path", required=True)
    p_mark.add_argument("--session-id", required=True)

    p_off = sub.add_parser("commit-offset")
    p_off.add_argument("--agent-started", choices=("true", "false"), required=True)
    p_off.add_argument("--exit-code", default="")
    p_off.add_argument("--current-offset", type=int, required=True)
    p_off.add_argument("--next-offset", type=int, required=True)

    # FR #213 monitor restart backoff + live tree guard
    p_bo = sub.add_parser("monitor-backoff-delay")
    p_bo.add_argument("--n", type=int, required=True)

    p_bs = sub.add_parser("monitor-note-start")
    p_bs.add_argument("--home", required=True)

    p_be = sub.add_parser("monitor-note-exit")
    p_be.add_argument("--home", required=True)

    p_bh = sub.add_parser("monitor-note-healthy")
    p_bh.add_argument("--home", required=True)

    p_bw = sub.add_parser("monitor-wait")
    p_bw.add_argument("--home", required=True)

    p_lt = sub.add_parser("live-tree-check")
    p_lt.add_argument("--home", default="")
    p_lt.add_argument("--tree", default="")
    p_lt.add_argument("--role", default="monitor")
    p_lt.add_argument("--no-mark-start", action="store_true")

    args = parser.parse_args()

    if args.cmd == "select-sink":
        path, kind = select_listen_poll_sink(args.home)
        print(json.dumps({"path": str(path), "kind": kind}))
        return 0

    if args.cmd == "listen-health":
        exists, stale, mtime, path = listen_health_sink(
            args.home, stale_seconds=args.stale_seconds
        )
        print(
            json.dumps(
                {
                    "log_exists": exists,
                    "log_stale": stale,
                    "mtime_utc": mtime.isoformat() if mtime else None,
                    "listen_log_path": str(path) if path else None,
                }
            )
        )
        return 0

    if args.cmd == "read-from":
        if args.sink_path and args.sink_kind:
            sink_path = Path(args.sink_path)
            kind: ListenSinkKind = args.sink_kind  # type: ignore[assignment]
        else:
            sink_path, kind = select_listen_poll_sink(args.home)
        lines, next_off = read_new_from_lines(
            sink_path, args.offset, sink_kind=kind
        )
        print(json.dumps({"lines": lines, "next_offset": next_off}))
        return 0

    if args.cmd == "parse-cursor-session":
        try:
            text = Path(args.file).read_text(encoding="utf-8", errors="replace")
        except OSError:
            print("null")
            return 1
        sid = parse_cursor_session_id(text)
        print(sid if sid else "null")
        return 0

    if args.cmd == "cursor-bound":
        sid = read_session_id(args.session_path)
        print("true" if is_bound_cursor_session_id(sid, args.session_path) else "false")
        return 0

    if args.cmd == "format-wake":
        from_lines = [ln for ln in args.lines.splitlines() if ln.strip()]
        if (args.engine or "").strip().lower() == "aider":
            print(format_aider_wake_payload(from_lines, sink_name=args.sink_name))
        else:
            print(format_irc_wake_payload(from_lines, sink_name=args.sink_name))
        return 0

    if args.cmd == "mark-cursor-bound":
        write_cursor_bound_session(args.session_path, args.session_id)
        return 0

    if args.cmd == "commit-offset":
        started = args.agent_started == "true"
        code: int | None
        if args.exit_code == "":
            code = None
        else:
            code = int(args.exit_code)
        committed = commit_listen_offset_after_wake(
            agent_started=started,
            exit_code=code,
            current_offset=args.current_offset,
            next_offset=args.next_offset,
        )
        print(committed)
        return 0

    if args.cmd == "monitor-backoff-delay":
        import monitor_restart_backoff as mrb

        print(f"{mrb.delay_after_fast_exits(args.n):.3f}")
        return 0

    if args.cmd == "monitor-note-start":
        import monitor_restart_backoff as mrb
        from dataclasses import asdict

        print(json.dumps(asdict(mrb.note_start(args.home))))
        return 0

    if args.cmd == "monitor-note-exit":
        import monitor_restart_backoff as mrb
        from dataclasses import asdict

        st, delay = mrb.note_exit(args.home)
        print(json.dumps({**asdict(st), "delay_s": delay}))
        return 0

    if args.cmd == "monitor-note-healthy":
        import monitor_restart_backoff as mrb
        from dataclasses import asdict

        print(json.dumps(asdict(mrb.note_healthy(args.home))))
        return 0

    if args.cmd == "monitor-wait":
        import monitor_restart_backoff as mrb

        slept = mrb.sleep_before_repair(args.home)
        print(f"{slept:.3f}")
        return 0

    if args.cmd == "live-tree-check":
        import live_tree_guard
        from dataclasses import asdict

        snap = live_tree_guard.check_and_report(
            tree=args.tree or None,
            home=args.home or None,
            role=args.role,
            log=lambda m: print(m, flush=True),
            mark_start=not args.no_mark_start,
        )
        print(json.dumps(asdict(snap)))
        return 0 if snap.ok else 1

    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli())
