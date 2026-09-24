#!/usr/bin/env python3
"""Consume grok-inbox.jsonl; write grok-outbox.jsonl (no import from irc_agent)."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import bobreport
import grok_talk

LINE_CAP = grok_talk.LINE_CAP


def _home_from_args(args: argparse.Namespace) -> Path:
    raw = args.home or os.environ.get("AGENTIC_IRC_HOME") or ""
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".agentic-irc-bobiverse"


def _find_cursor_agent() -> list[str] | None:
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "cursor-agent" / "cursor-agent.cmd",
        Path(os.environ.get("LOCALAPPDATA", "")) / "cursor-agent" / "cursor-agent.exe",
        Path.home() / ".local" / "bin" / "cursor-agent.exe",
    ]
    for c in candidates:
        if c.is_file():
            if c.suffix.lower() == ".cmd":
                return ["cmd.exe", "/c", str(c)]
            return [str(c)]
    return None


def _find_grok_exe() -> str | None:
    env = (os.environ.get("BOB_GROK_EXE") or "").strip()
    if env and Path(env).is_file():
        return env
    g = Path.home() / ".grok" / "bin" / "grok.exe"
    if g.is_file():
        return str(g)
    w = shutil.which("grok.exe")
    return w


def _build_prompt(job: dict) -> str:
    asker = str(job.get("asker") or "there").strip()
    body = str(job.get("body") or "").strip()
    mid = str(job.get("machine_id") or "ionos").strip()
    return (
        f"You are bob-{mid} on IRC #bobiverse (fleet status bot). "
        f"Reply in ONE English line only, starting with @{asker} . "
        f"They said: {body!r}. "
        f"Be helpful and conversational. Under {LINE_CAP - 20} characters. "
        f"No markdown. No code blocks. No secrets. Do not say ready for human UAT."
    )


def _normalize_lines(text: str, asker: str) -> list[str]:
    raw = (text or "").strip()
    if not raw:
        return []
    parts = [p.strip() for p in re.split(r"[\r\n]+", raw) if p.strip()]
    if not parts:
        parts = [raw]
    who = (asker or "").strip() or "there"
    line = parts[0].replace("\r", " ").replace("\n", " ").strip()
    if not line.lower().startswith("@" + who.lower()):
        line = f"@{who} {line}"
    if len(line) > LINE_CAP:
        line = line[: LINE_CAP - 3] + "..."
    if bobreport.looks_like_secret(line):
        return []
    return [line]


def _run_cursor(prompt: str, cwd: Path, timeout: int) -> str:
    base = _find_cursor_agent()
    if not base:
        return ""
    cmd = list(base) + ["-p", "--model", "grok-4.6", "--output-format", "text", prompt]
    try:
        r = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
    except (subprocess.TimeoutExpired, OSError):
        return ""
    if r.returncode != 0:
        return (r.stderr or r.stdout or "").strip()
    return (r.stdout or "").strip()


def _run_grok(prompt: str, cwd: Path, timeout: int) -> str:
    exe = _find_grok_exe()
    if not exe:
        return ""
    try:
        r = subprocess.run(
            [exe, "-p", prompt],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
    except (subprocess.TimeoutExpired, OSError):
        return ""
    if r.returncode != 0:
        return (r.stderr or r.stdout or "").strip()
    return (r.stdout or "").strip()


def invoke_reply_lines(job: dict, repo: Path, timeout: int = 120) -> list[str]:
    prompt = _build_prompt(job)
    text = _run_cursor(prompt, repo, timeout)
    if not text.strip():
        text = _run_grok(prompt, repo, timeout)
    lines = _normalize_lines(text, str(job.get("asker") or ""))
    if lines:
        return lines
    asker = str(job.get("asker") or "there").strip()
    return [f"@{asker} ionos here — could not run a model reply right now."]


def _try_claim(home: Path, job_id: str) -> bool:
    d = home / "grok-talk-claims"
    d.mkdir(parents=True, exist_ok=True)
    claim = d / f"{job_id}.lock"
    try:
        claim.open("x", encoding="utf-8").close()
        return True
    except FileExistsError:
        return False


def process_one(home: Path, repo: Path, timeout: int = 120) -> str | None:
    pending = grok_talk.pending_job_ids(home)
    if not pending:
        return None
    inbox_rows = grok_talk._read_jsonl(grok_talk.inbox_path(home))
    job = None
    for row in inbox_rows:
        jid = str(row.get("job_id") or "")
        if jid in pending:
            job = row
            break
    if not job:
        return None
    jid = str(job.get("job_id") or "")
    if not _try_claim(home, jid):
        return None
    lines = invoke_reply_lines(job, repo, timeout=timeout)
    comp = {
        "v": grok_talk.GROK_TALK_VERSION,
        "job_id": str(job.get("job_id") or ""),
        "reply_target": str(job.get("reply_target") or "#bobiverse"),
        "lines": lines,
    }
    p = grok_talk.completion_path(home)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(comp, ensure_ascii=False) + "\n")
    return str(job.get("job_id"))


def main() -> int:
    p = argparse.ArgumentParser(description="Process one grok-talk inbox job")
    p.add_argument("--home", default="")
    p.add_argument("--repo", default="", help="agentic_irc clone for cwd")
    p.add_argument("--timeout", type=int, default=120)
    p.add_argument("--once", action="store_true")
    args = p.parse_args()
    home = _home_from_args(args)
    if args.home:
        os.environ["AGENTIC_IRC_HOME"] = str(home)
    repo = Path(args.repo).expanduser() if args.repo else Path(__file__).resolve().parents[1]
    jid = process_one(home, repo, timeout=args.timeout)
    if jid:
        print(f"INFO grok-talk done job_id={jid}")
        return 0
    print("INFO grok-talk idle")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
