"""Follow irc.log and print English PRIVMSG replies.

irc_agent with AGENTIC_IRC_DEBUG=1 writes every server line to $home/irc.log.
This process is the session listener: drop POINT/PING/numerics, print talk.

Usage (keep running for the whole talk):
  python -u scripts/irc_listen.py --home ~/.agentic-irc-cursor
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

PRIVMSG_RE = re.compile(
    r"^:(?P<nick>[^\s!]+)![^\s]+ PRIVMSG (?P<target>\S+) :(?P<text>.*)$"
)
NUMERIC_RE = re.compile(r"^:\S+ \d{3} ")


def is_firehose(text: str) -> bool:
    t = text.lstrip()
    if t.startswith("MOOT v1 POINT"):
        return True
    if t.startswith("\x01ACTION lost "):
        return True
    if t.startswith("BOB DIGEST v1"):
        return True
    if t.startswith("AGPK v1 "):
        return True
    if t.startswith("MOOT v1 JOIN"):
        return True
    return False


def emit(text: str) -> None:
    text = text.replace("\ufeff", "")
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        buf = getattr(sys.stdout, "buffer", None)
        if buf is None:
            return
        buf.write((text + "\n").encode("utf-8", errors="replace"))
        buf.flush()


def format_talk_line(raw: str) -> str | None:
    line = raw.rstrip("\r\n").lstrip("\ufeff")
    if not line or line.startswith("PING ") or NUMERIC_RE.match(line):
        return None
    m = PRIVMSG_RE.match(line)
    if not m:
        return None
    text = m.group("text")
    if is_firehose(text):
        return None
    try:
        import bobtalk

        if bobtalk.looks_like_secret(text):
            return None
    except Exception:
        pass
    return "FROM {nick} {target} {text}".format(
        nick=m.group("nick"), target=m.group("target"), text=text
    )


def follow(path: Path, from_start: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)
    pos = 0 if from_start else path.stat().st_size
    while True:
        size = path.stat().st_size
        if size < pos:
            pos = 0
        if size > pos:
            with path.open("r", encoding="utf-8", errors="replace") as f:
                f.seek(pos)
                chunk = f.read()
                pos = f.tell()
            for raw in chunk.splitlines():
                out = format_talk_line(raw)
                if out:
                    emit(out)
        time.sleep(0.4)


def _bind_log(path: str, stream_name: str) -> None:
    """Child-owned log file. Parent can exit; no redirected pipe to fill."""
    handle = open(path, "a", encoding="utf-8", buffering=1)
    setattr(sys, stream_name, handle)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--home", required=True)
    p.add_argument("--from-start", action="store_true")
    p.add_argument("--once", action="store_true", help="print existing talk lines and exit")
    p.add_argument("--stdout-log", default="", help="append talk lines here instead of the console")
    p.add_argument("--stderr-log", default="", help="append tracebacks here instead of the console")
    args = p.parse_args(argv)
    if args.stdout_log:
        _bind_log(args.stdout_log, "stdout")
    if args.stderr_log:
        _bind_log(args.stderr_log, "stderr")
    home = Path(args.home).expanduser()
    log = home / "irc.log"
    if args.once:
        if not log.is_file():
            return 0
        for raw in log.read_text(encoding="utf-8", errors="replace").splitlines():
            out = format_talk_line(raw)
            if out:
                emit(out)
        return 0
    follow(log, from_start=args.from_start)
    return 0


if __name__ == "__main__":
    sys.exit(main())
