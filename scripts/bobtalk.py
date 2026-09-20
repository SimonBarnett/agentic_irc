#!/usr/bin/env python3
"""Conversational English lines from bob-peers JSON (one fact per line)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import bobstat

FLEET_MOOT_ID = "b0b1be15e0000001"
FLEET_MACHINE_ORDER = ("flamingo", "marchhare", "ionos", "ce-priority-dev1")
BOBIVERSE_CMD = "!bobiverse"
BOBIVERSE_COOLDOWN_S = 60.0

_ID_ALIASES = {"dev1": "ce-priority-dev1", "ce-priority-dev1": "ce-priority-dev1"}


def display_id(machine_id: str) -> str:
    mid = str(machine_id or "").strip()
    if mid == "ce-priority-dev1":
        return "dev1"
    return mid or "?"


def briefer_nick(moot_state: dict) -> str | None:
    """Chair if bob-*, else first bob-* on roster."""
    roster = list(moot_state.get("roster") or [])
    chair = str(moot_state.get("chair") or "").strip()
    if chair.lower().startswith("bob-"):
        return chair
    for nick in roster:
        if str(nick).lower().startswith("bob-"):
            return str(nick)
    return None


def is_briefer(moot_state: dict, live_nick: str) -> bool:
    bn = briefer_nick(moot_state)
    if bn:
        return live_nick.lower() == bn.lower()
    return live_nick.lower().startswith("bob-")


def parse_bobiverse_command(body: str) -> bool:
    text = (body or "").strip()
    if not text:
        return False
    return text.split(None, 1)[0].lower() == BOBIVERSE_CMD


def _resolve_peer_id(home: Path, machine_id: str) -> dict | None:
    mid = _ID_ALIASES.get(machine_id, machine_id)
    peer = bobstat.read_peer(home, mid)
    if peer:
        return peer
    if mid != machine_id:
        return bobstat.read_peer(home, machine_id)
    return None


def list_fleet_peers(home: Path) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for mid in FLEET_MACHINE_ORDER:
        peer = _resolve_peer_id(home, mid)
        if peer and peer.get("id") not in seen:
            out.append(peer)
            seen.add(str(peer.get("id")))
    d = bobstat.peers_dir(home)
    if d.is_dir():
        for path in sorted(d.glob("*.json")):
            try:
                doc = bobstat.read_peer(home, path.stem)
            except OSError:
                continue
            if doc and str(doc.get("id")) not in seen:
                out.append(doc)
                seen.add(str(doc.get("id")))
    return out


def _running_job(peer: dict) -> dict | None:
    for j in list(peer.get("jobs") or []):
        if str(j.get("state", "")).lower() == "running":
            return j
    return None


def _infer_model(peer: dict) -> str | None:
    model = peer.get("model")
    if model:
        return str(model)
    cur = peer.get("cursor_label")
    if cur and str(cur) not in ("", "-", "empty"):
        return "Cursor Models"
    job = _running_job(peer)
    if job:
        repo = str(job.get("repo") or "")
        if repo == "grok.exe":
            return "grok.exe"
    run = int(peer.get("running") or 0)
    if run > 0:
        return "grok.exe"
    return None


def _short_sha(sha: str) -> str:
    s = str(sha or "").strip()
    if len(s) > 7:
        return s[:7]
    return s


def _human_duration(peer: dict) -> str | None:
    dur = peer.get("duration")
    if dur:
        return str(dur)
    started = peer.get("started_at") or peer.get("started")
    if not started:
        return None
    try:
        if isinstance(started, (int, float)):
            t0 = datetime.fromtimestamp(float(started), tz=timezone.utc)
        else:
            raw = str(started).replace("Z", "+00:00")
            t0 = datetime.fromisoformat(raw)
            if t0.tzinfo is None:
                t0 = t0.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None
    secs = max(0, int((datetime.now(timezone.utc) - t0).total_seconds()))
    if secs < 90:
        return f"{secs} seconds"
    mins = secs // 60
    if mins < 90:
        return f"{mins} minutes" if mins != 1 else "1 minute"
    hours = mins // 60
    if hours == 1:
        return "an hour"
    return f"{hours} hours"


def _kind_phrase(kind: str, repo: str) -> str | None:
    k = (kind or "").strip().lower()
    if not repo:
        return None
    if k == "mrb":
        return f"That's an MRB of {repo}."
    if k == "uat":
        return f"That's UAT on {repo}."
    if k == "worker":
        return f"That's a worker on {repo}."
    return f"Working on {repo}."


def peer_talk_lines(peer: dict | None) -> list[str]:
    """One conversational fact per list entry for a single machine."""
    if not peer:
        return []
    mid = display_id(str(peer.get("id") or "?"))
    running = int(peer.get("running") or 0)
    queued = int(peer.get("queued") or 0)
    job = _running_job(peer)
    busy = running > 0 or queued > 0 or job is not None

    if not busy:
        return [f"{mid} is idle."]

    lines: list[str] = []
    model = _infer_model(peer)
    if model:
        lines.append(f"{mid} is on {model} now.")

    kind = peer.get("kind")
    repo = peer.get("repo") or (job.get("repo") if job else None)
    phrase = _kind_phrase(str(kind) if kind else "", str(repo) if repo else "")
    if phrase:
        lines.append(phrase)
    elif repo:
        lines.append(f"Working on {repo}.")

    sha = peer.get("sha")
    if sha:
        lines.append(f"SHA is {_short_sha(str(sha))}.")

    duration = _human_duration(peer)
    hung = peer.get("hung")
    if hung is True or str(hung).lower() in ("1", "true", "yes"):
        if duration:
            lines.append(f"About {duration} in, looks hung.")
        else:
            lines.append(f"{mid} looks hung.")
    elif duration:
        resp = peer.get("responding")
        if resp is False or str(resp).lower() in ("0", "false", "no"):
            lines.append(f"About {duration} in, not responding.")
        else:
            lines.append(f"About {duration} in, still responding.")
    elif queued > 0 and running == 0:
        lines.append(f"{mid} has {queued} queued.")

    return lines or [f"{mid} is busy."]


def network_talk_lines(home: Path) -> list[str]:
    """Current fleet picture: one fact per line across machines."""
    lines: list[str] = []
    peers = list_fleet_peers(home)
    if not peers:
        return ["No bob-peers status on this box yet."]
    for peer in peers:
        lines.extend(peer_talk_lines(peer))
    return lines


def change_talk_line(before: dict | None, after: dict) -> str | None:
    """One short channel line when a named field flips (not lastSeen-only)."""
    if not after:
        return None
    mid = display_id(str(after.get("id") or "?"))
    if before is None:
        return peer_talk_lines(after)[0]

    def _sig(doc: dict) -> str:
        parts = [
            str(doc.get("model") or ""),
            str(doc.get("kind") or ""),
            str(doc.get("repo") or ""),
            str(doc.get("sha") or ""),
            str(doc.get("hung") or ""),
            str(doc.get("responding") or ""),
            str(int(doc.get("running") or 0)),
            str(int(doc.get("queued") or 0)),
        ]
        job = _running_job(doc)
        if job:
            parts.append(str(job.get("repo") or ""))
        return "|".join(parts)

    if _sig(before) == _sig(after):
        return None
    new_lines = peer_talk_lines(after)
    return new_lines[0] if new_lines else None
