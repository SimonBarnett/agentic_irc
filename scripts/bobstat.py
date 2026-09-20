#!/usr/bin/env python3
"""Cleartext BOB v1 fleet status on a MODE2 moot POINT (not a secret).

Wire (trailing text of MOOT v1 POINT <id> :<text>, <=350 chars):

    BOB v1 id=flamingo weekly=96 running=0 queued=0 lastSeen=2026-09-20T08:31:16Z jobs=-

jobs is '-' or comma-separated repo:state (no spaces). Weekly is that
machine's own Grok weekly remaining percent, or '-' if unknown.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

BOB_PREFIX = "BOB v1 "
MAX_POINT = 350
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
JOB_RE = re.compile(r"^[A-Za-z0-9._+/-]+:[A-Za-z0-9_-]+$")


def parse_bob_point(text: str) -> dict | None:
    raw = (text or "").strip()
    if not raw.startswith(BOB_PREFIX):
        return None
    body = raw[len(BOB_PREFIX) :].strip()
    kv: dict[str, str] = {}
    for tok in body.split():
        if "=" not in tok:
            return None
        k, _, v = tok.partition("=")
        kv[k] = v
    mid = kv.get("id", "")
    if not ID_RE.match(mid):
        return None
    jobs_raw = kv.get("jobs", "-")
    jobs: list[dict] = []
    if jobs_raw and jobs_raw != "-":
        for part in jobs_raw.split(","):
            if not JOB_RE.match(part):
                continue
            repo, _, state = part.partition(":")
            jobs.append({"repo": repo, "state": state, "machine": mid})
    weekly = kv.get("weekly", "-")
    weekly_pct = None
    if weekly not in ("", "-"):
        try:
            n = int(weekly)
            if 0 <= n <= 100:
                weekly_pct = n
        except ValueError:
            weekly_pct = None
    running = 0
    queued = 0
    try:
        running = int(kv.get("running", "0"))
        queued = int(kv.get("queued", "0"))
    except ValueError:
        return None
    return {
        "ok": True,
        "id": mid,
        "weekly": weekly_pct,
        "running": running,
        "queued": queued,
        "lastSeen": kv.get("lastSeen") or None,
        "jobs": jobs,
        "source": "irc",
    }


def format_bob_point(doc: dict) -> str:
    mid = str(doc.get("id") or "")
    if not ID_RE.match(mid):
        raise ValueError("invalid machine id")
    weekly = doc.get("weekly")
    if weekly is None or weekly == "":
        w = "-"
    else:
        w = str(int(weekly))
    jobs = []
    for j in list(doc.get("jobs") or []):
        repo = str(j.get("repo") or "").replace(" ", "")
        state = str(j.get("state") or "running").replace(" ", "")
        if repo and state and JOB_RE.match(f"{repo}:{state}"):
            jobs.append(f"{repo}:{state}")
    job_s = ",".join(jobs) if jobs else "-"
    seen = str(doc.get("lastSeen") or "-")
    line = (
        f"{BOB_PREFIX}id={mid} weekly={w} running={int(doc.get('running') or 0)} "
        f"queued={int(doc.get('queued') or 0)} lastSeen={seen} jobs={job_s}"
    )
    if len(line) > MAX_POINT:
        line = line[: MAX_POINT - 1] + "-"
    return line


def peers_dir(home: Path) -> Path:
    d = Path(home) / "bob-peers"
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_peer(home: Path, doc: dict) -> Path | None:
    parsed = doc if doc.get("ok") and doc.get("id") else parse_bob_point(str(doc.get("text") or ""))
    if not parsed:
        return None
    path = peers_dir(home) / (parsed["id"] + ".json")
    path.write_text(json.dumps(parsed, indent=2) + "\n", encoding="utf-8")
    return path


def read_peer(home: Path, machine_id: str) -> dict | None:
    path = peers_dir(home) / (machine_id + ".json")
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
