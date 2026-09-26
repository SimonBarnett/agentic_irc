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


def format_talk_line(
    raw: str,
    *,
    from_accounts: set[str] | None = None,
    accounts: dict[str, str] | None = None,
    include_account: bool = False,
) -> str | None:
    line = raw.rstrip("\r\n").lstrip("\ufeff")
    if not line or line.startswith("PING ") or NUMERIC_RE.match(line):
        return None
    try:
        from account_map import account_from_tags, parse_message_tags
    except Exception:
        parse_message_tags = None  # type: ignore[assignment]
        account_from_tags = None  # type: ignore[assignment]
    tags: dict[str, str] = {}
    wire = line
    if parse_message_tags is not None:
        tags, wire = parse_message_tags(line)
    m = PRIVMSG_RE.match(wire)
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
    nick = m.group("nick")
    acct = None
    if account_from_tags is not None:
        acct = account_from_tags(tags)
    if acct is None and accounts:
        acct = accounts.get(nick.lower())
    if from_accounts is not None:
        # Opt-in filter: require a known logged-in account in the allow-list.
        if not acct or acct.lower() not in from_accounts:
            return None
    if include_account and acct:
        return "FROM {nick} {target} account={acct} {text}".format(
            nick=nick, target=m.group("target"), acct=acct, text=text
        )
    return "FROM {nick} {target} {text}".format(
        nick=nick, target=m.group("target"), text=text
    )


def load_accounts(home: Path) -> dict[str, str]:
    path = home / "accounts.json"
    if not path.is_file():
        return {}
    try:
        import json

        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k).lower(): str(v) for k, v in data.items() if k and v}
    except Exception:
        return {}
    return {}


def follow(
    path: Path,
    from_start: bool = False,
    *,
    home: Path | None = None,
    from_accounts: set[str] | None = None,
    include_account: bool = False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)
    pos = 0 if from_start else path.stat().st_size
    while True:
        size = path.stat().st_size
        if size < pos:
            pos = 0
        if size > pos:
            accounts = load_accounts(home) if home is not None else {}
            with path.open("r", encoding="utf-8", errors="replace") as f:
                f.seek(pos)
                chunk = f.read()
                pos = f.tell()
            for raw in chunk.splitlines():
                out = format_talk_line(
                    raw,
                    from_accounts=from_accounts,
                    accounts=accounts,
                    include_account=include_account,
                )
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
    p.add_argument(
        "--from-account",
        action="append",
        default=[],
        dest="from_accounts",
        help="only emit FROM lines whose sender is logged in as this account (repeatable)",
    )
    p.add_argument(
        "--include-account",
        action="store_true",
        help="opt-in: emit account=<acct> in FROM lines when known (default format unchanged)",
    )
    p.add_argument("--stdout-log", default="", help="append talk lines here instead of the console")
    p.add_argument("--stderr-log", default="", help="append tracebacks here instead of the console")
    args = p.parse_args(argv)
    if args.stdout_log:
        _bind_log(args.stdout_log, "stdout")
    if args.stderr_log:
        _bind_log(args.stderr_log, "stderr")
    home = Path(args.home).expanduser()
    log = home / "irc.log"
    from_accounts = {a.lower() for a in (args.from_accounts or []) if a} or None
    include_account = bool(args.include_account)
    if args.once:
        if not log.is_file():
            return 0
        accounts = load_accounts(home)
        for raw in log.read_text(encoding="utf-8", errors="replace").splitlines():
            out = format_talk_line(
                raw,
                from_accounts=from_accounts,
                accounts=accounts,
                include_account=include_account,
            )
            if out:
                emit(out)
        return 0
    follow(
        log,
        from_start=args.from_start,
        home=home,
        from_accounts=from_accounts,
        include_account=include_account,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
