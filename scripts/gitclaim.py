#!/usr/bin/env python3
"""Deterministic GIT claim queue for Jeeves. No model calls.

Webhook path appends claimable work to git-unaccepted.json on the digest
home. A shop worker sends !BORED; Jeeves offers the oldest row as
!TASK {repo} {task} {id}. !ACCEPT {repo} {task} {id} stamps git-accepted.jsonl
and removes the row. FILE v1 ACCEPT is a different protocol.
"""
from __future__ import annotations

import json
import os
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import bobreport

IDLE_S = 120.0
UNACCEPTED_NAME = "git-unaccepted.json"
ACCEPTED_NAME = "git-accepted.jsonl"
ACTIVITY_NAME = "git-worker-activity.json"
LOCK_NAME = "git-claim.lock"

# issues opened → PR (issue→implement pipeline). Not BUILD.
# pull_request opened / ready_for_review → MRB.
CLAIM_ACTIONS: dict[tuple[str, str], str] = {
    ("issues", "opened"): "PR",
    ("pull_request", "opened"): "MRB",
    ("pull_request", "ready_for_review"): "MRB",
}
TASKS = frozenset(CLAIM_ACTIONS.values())

REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
ID_RE = re.compile(r"^#\d+$")

NAK_BORED_WAIT = "NAK !BORED wait"
NAK_BORED_BUSY = "NAK !BORED busy"
NAK_BORED_EMPTY = "NAK !BORED empty"


@dataclass(frozen=True)
class GitClaim:
    repo: str
    task: str
    id: str
    event: str
    action: str
    line: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _root(home: Path) -> Path:
    return bobreport.fleet_digest_home(Path(home))


def unaccepted_path(home: Path) -> Path:
    return _root(home) / UNACCEPTED_NAME


def accepted_path(home: Path) -> Path:
    return _root(home) / ACCEPTED_NAME


def activity_path(home: Path) -> Path:
    return _root(home) / ACTIVITY_NAME


def format_task(repo: str, task: str, ident: str) -> str:
    return f"!TASK {repo} {task} {ident}"


def format_accept_ok(repo: str, task: str, ident: str) -> str:
    return f"OK !ACCEPT {repo} {task} {ident}"


def format_accept_nak(repo: str, task: str, ident: str) -> str:
    return f"NAK !ACCEPT {repo} {task} {ident}"


def is_bored_command(body: str) -> bool:
    return (body or "").strip().lower() == "!bored"


def is_accept_command(body: str) -> bool:
    parts = (body or "").strip().split(None, 1)
    return bool(parts) and parts[0].lower() == "!accept"


def parse_accept(body: str) -> tuple[str, str, str] | None:
    """Fixed shape: !ACCEPT {owner/repo} {PR|MRB} {#n}. Not FILE v1 ACCEPT."""
    parts = (body or "").strip().split()
    if len(parts) != 4 or parts[0].lower() != "!accept":
        return None
    repo, task, ident = parts[1], parts[2], parts[3]
    if task not in TASKS or not REPO_RE.fullmatch(repo) or not ID_RE.fullmatch(ident):
        return None
    return repo, task, ident


def parse_git_announce(line: str) -> GitClaim | None:
    """Parse a Jeeves `GIT …` line. None for ping, push, and other noise."""
    text = (line or "").strip()
    if not text.startswith(bobreport.GIT_ANNOUNCE_PREFIX):
        return None
    parts = text.split()
    if len(parts) < 5:
        return None
    event = parts[1].lower()
    repo = parts[2]
    action = parts[3].lower()
    ident = parts[4]
    task = CLAIM_ACTIONS.get((event, action))
    if task is None or not REPO_RE.fullmatch(repo) or not ID_RE.fullmatch(ident):
        return None
    return GitClaim(repo=repo, task=task, id=ident, event=event, action=action, line=text)


def _payload_repo(payload: dict) -> str:
    repo = payload.get("repository")
    if isinstance(repo, dict):
        return str(repo.get("full_name") or "").strip()
    return ""


def _payload_number(event: str, payload: dict) -> str | None:
    key = "pull_request" if event == "pull_request" else "issue" if event == "issues" else ""
    ent = payload.get(key) if key else None
    if not isinstance(ent, dict):
        return None
    num = ent.get("number")
    if isinstance(num, bool) or num is None:
        return None
    try:
        n = int(num)
    except (TypeError, ValueError):
        return None
    if n < 1:
        return None
    return f"#{n}"


def claim_from_payload(event: str, payload: dict, *, line: str = "") -> GitClaim | None:
    """Build a claim from the GitHub webhook body. None if not on the allowlist."""
    if not isinstance(payload, dict):
        return None
    ev = (event or "").strip().lower()
    action = str(payload.get("action") or "").strip().lower()
    task = CLAIM_ACTIONS.get((ev, action))
    if task is None:
        return None
    repo = _payload_repo(payload)
    ident = _payload_number(ev, payload)
    if not repo or ident is None or not REPO_RE.fullmatch(repo):
        return None
    src = (line or "").strip()
    return GitClaim(repo=repo, task=task, id=ident, event=ev, action=action, line=src)


def canonical_worker_nick(nick: str) -> str | None:
    parsed = bobreport.parse_worker_nick(nick)
    if not parsed:
        return None
    try:
        return bobreport.worker_nick(parsed[0], parsed[1])
    except ValueError:
        return None


def _channel(target: str) -> str:
    return bobreport.normalize_channel(target).lower()


def worker_shop_channel(nick: str) -> str | None:
    parsed = bobreport.parse_worker_nick(nick)
    if not parsed:
        return None
    try:
        return bobreport.shop_channel(parsed[0]).lower()
    except ValueError:
        return None


def _bob_shop_channel(nick: str) -> str | None:
    mid = bobreport.machine_from_nick(nick)
    if not mid or not str(nick or "").strip().lower().startswith("bob-"):
        return None
    try:
        return bobreport.shop_channel(mid).lower()
    except ValueError:
        return None


def accept_allowed(nick: str, channel: str) -> bool:
    """w-* or bob-* on their shop or on #bobiverse."""
    ch = _channel(channel)
    fleet = bobreport.FLEET_CHANNEL.lower()
    shop = worker_shop_channel(nick) or _bob_shop_channel(nick)
    if shop is None:
        return False
    return ch in (shop, fleet)


def worker_working_on(home: Path, nick: str) -> str:
    """Digest working_on for this worker pid. Empty if the worker is absent."""
    parsed = bobreport.parse_worker_nick(nick)
    if not parsed:
        return ""
    mid, pid = parsed
    doc = bobreport.load_digest(_root(home))
    machines = doc.get("machines") if isinstance(doc.get("machines"), dict) else {}
    ent = machines.get(mid) if isinstance(machines.get(mid), dict) else {}
    workers = ent.get("workers") if isinstance(ent.get("workers"), dict) else {}
    row = workers.get(str(pid))
    if not isinstance(row, dict):
        return ""
    return str(row.get("working_on") or "").strip()


@contextmanager
def _lock(home: Path):
    root = _root(home)
    root.mkdir(parents=True, exist_ok=True)
    path = root / LOCK_NAME
    deadline = time.time() + 5.0
    fd: int | None = None
    while fd is None:
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                if time.time() - path.stat().st_mtime > 30:
                    path.unlink()
                    continue
            except OSError:
                pass
            if time.time() > deadline:
                raise TimeoutError("git-claim lock")
            time.sleep(0.02)
    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)
        try:
            path.unlink()
        except OSError:
            pass


def _read_items(path: Path) -> list[dict]:
    if not path.exists():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError("git-unaccepted")
    items = doc.get("items")
    if not isinstance(items, list):
        raise ValueError("git-unaccepted items")
    out: list[dict] = []
    for row in items:
        if isinstance(row, dict):
            out.append(row)
    return out


def _write_items(path: Path, items: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"v": 1, "items": items}, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _same(row: dict, repo: str, task: str, ident: str) -> bool:
    return row.get("repo") == repo and row.get("task") == task and row.get("id") == ident


def _read_accepted(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        text = raw.strip()
        if not text:
            continue
        try:
            row = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _already(items: list[dict], accepted: list[dict], repo: str, task: str, ident: str) -> bool:
    return any(_same(row, repo, task, ident) for row in items) or any(
        _same(row, repo, task, ident) for row in accepted
    )


def enqueue_unaccepted(home: Path, claim: GitClaim) -> str:
    """Append FIFO. Returns added, duplicate, or error."""
    try:
        with _lock(home):
            path = unaccepted_path(home)
            done = accepted_path(home)
            try:
                items = _read_items(path)
                accepted = _read_accepted(done)
            except (OSError, json.JSONDecodeError, ValueError):
                return "error"
            if _already(items, accepted, claim.repo, claim.task, claim.id):
                return "duplicate"
            seq = 1
            for row in items:
                try:
                    seq = max(seq, int(row.get("seq") or 0) + 1)
                except (TypeError, ValueError):
                    continue
            items.append(
                {
                    "repo": claim.repo,
                    "task": claim.task,
                    "id": claim.id,
                    "ts": _utc_now(),
                    "line": claim.line,
                    "event": claim.event,
                    "action": claim.action,
                    "seq": seq,
                }
            )
            try:
                _write_items(path, items)
            except OSError:
                return "error"
            return "added"
    except (TimeoutError, OSError):
        return "error"


def load_unaccepted(home: Path) -> list[dict]:
    with _lock(home):
        return _read_items(unaccepted_path(home))


def next_unaccepted(home: Path) -> dict | None:
    """Oldest seq, then ts, repo, task, id. No ranking."""
    try:
        items = load_unaccepted(home)
    except (OSError, json.JSONDecodeError, ValueError, TimeoutError):
        return None
    if not items:
        return None

    def _key(row: dict) -> tuple:
        try:
            seq = int(row.get("seq") or 0)
        except (TypeError, ValueError):
            seq = 0
        return (seq, str(row.get("ts") or ""), str(row.get("repo") or ""), str(row.get("task") or ""), str(row.get("id") or ""))

    return sorted(items, key=_key)[0]


def mark_accepted(
    home: Path,
    repo: str,
    task: str,
    ident: str,
    *,
    nick: str,
    channel: str,
) -> str:
    """Remove one unaccepted row and append a stamp. ok, duplicate, missing, or error."""
    try:
        with _lock(home):
            path = unaccepted_path(home)
            done = accepted_path(home)
            try:
                items = _read_items(path)
                accepted = _read_accepted(done)
            except (OSError, json.JSONDecodeError, ValueError):
                return "error"
            kept = [row for row in items if not _same(row, repo, task, ident)]
            if len(kept) != len(items):
                already = any(_same(row, repo, task, ident) for row in accepted)
                try:
                    if not already:
                        stamp = {
                            "repo": repo,
                            "task": task,
                            "id": ident,
                            "nick": (nick or "").strip(),
                            "channel": bobreport.normalize_channel(channel),
                            "ts": _utc_now(),
                        }
                        done.parent.mkdir(parents=True, exist_ok=True)
                        with done.open("a", encoding="utf-8") as fh:
                            fh.write(json.dumps(stamp, separators=(",", ":")) + "\n")
                    _write_items(path, kept)
                except OSError:
                    return "error"
                return "duplicate" if already else "ok"
            if any(_same(row, repo, task, ident) for row in accepted):
                return "duplicate"
            return "missing"
    except (TimeoutError, OSError):
        return "error"


def load_accepted(home: Path) -> list[dict]:
    with _lock(home):
        return _read_accepted(accepted_path(home))


def _read_activity(path: Path) -> dict[str, float]:
    if not path.exists():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    seen = doc.get("seen") if isinstance(doc, dict) else None
    if not isinstance(seen, dict):
        return {}
    out: dict[str, float] = {}
    for key, val in seen.items():
        try:
            out[str(key)] = float(val)
        except (TypeError, ValueError):
            continue
    return out


def _write_activity(path: Path, seen: dict[str, float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"v": 1, "seen": seen}, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def note_worker_activity(home: Path, nick: str, now: float) -> None:
    canon = canonical_worker_nick(nick)
    if not canon:
        return
    try:
        with _lock(home):
            path = activity_path(home)
            try:
                seen = _read_activity(path)
            except (OSError, json.JSONDecodeError):
                seen = {}
            seen[canon] = float(now)
            _write_activity(path, seen)
    except (TimeoutError, OSError, json.JSONDecodeError):
        return


def last_worker_activity(home: Path, nick: str) -> float | None:
    canon = canonical_worker_nick(nick)
    if not canon:
        return None
    try:
        with _lock(home):
            seen = _read_activity(activity_path(home))
    except (OSError, json.JSONDecodeError, TimeoutError, ValueError):
        return None
    val = seen.get(canon)
    return float(val) if val is not None else None


def bored_gate(home: Path, nick: str, channel: str, now: float) -> str:
    """ignore, wait, busy, or ok. wait is checked before busy so retries stay quiet."""
    if worker_shop_channel(nick) is None:
        return "ignore"
    if _channel(channel) != worker_shop_channel(nick):
        return "ignore"
    last = last_worker_activity(home, nick)
    if last is not None and (float(now) - last) < IDLE_S:
        return "wait"
    if worker_working_on(home, nick):
        return "busy"
    return "ok"
