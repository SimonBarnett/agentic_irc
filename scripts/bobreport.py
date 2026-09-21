#!/usr/bin/env python3
"""!report status ingest and !bobiverse JSON digest (issue #36)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import bobstat

REPORT_CMD = "!report"
DIGEST_PREFIX = "BOB DIGEST v1 "
MAX_DIGEST_LINE = 350
SHA_RE = re.compile(r"^([0-9a-fA-F]{7,}|-)$")
ID_ALIASES = {"dev1": "ce-priority-dev1", "ce-priority-dev1": "ce-priority-dev1"}

NICK_TO_MACHINE: dict[str, str] = {
    "bob-flamingo": "flamingo",
    "bob-marchhare": "marchhare",
    "bob-ionos": "ionos",
    "bob-dev1": "ce-priority-dev1",
}

HELP_TEXT = (
    "!report TASK START|STOP <repo> <sha> <model> <desc> <runtime>\n"
    "!report PCENT <machine> <source> <n%>\n"
    "!report UPTIME <since-iso>\n"
    "!bobiverse  → JSON digest (whisper)"
)


def looks_like_secret(text: str) -> bool:
    lower = (text or "").lower()
    return "password=" in lower or "xai_api_key=" in lower


def normalize_machine_id(raw: str) -> str | None:
    mid = str(raw or "").strip().lower()
    if not mid or mid == "nope":
        return None
    mid = ID_ALIASES.get(mid, mid)
    if not bobstat.ID_RE.match(mid):
        return None
    return mid


def machine_from_nick(nick: str) -> str | None:
    n = (nick or "").strip().lower()
    if n in NICK_TO_MACHINE:
        return NICK_TO_MACHINE[n]
    if n.startswith("bob-"):
        return normalize_machine_id(n[4:])
    return None


def nick_for_machine(doc_machines: dict, machine_id: str) -> str:
    mid = normalize_machine_id(machine_id) or machine_id
    for nick, mid_map in NICK_TO_MACHINE.items():
        if mid_map == mid:
            return nick
    return f"bob-{mid}" if mid != "ce-priority-dev1" else "bob-dev1"


def parse_report_command(body: str) -> bool:
    text = (body or "").strip()
    if not text:
        return False
    return text.split(None, 1)[0].lower() == REPORT_CMD


def digest_path(home: Path) -> Path:
    return Path(home) / "digest.json"


def empty_digest() -> dict:
    return {"v": 1, "ts": "", "briefer": "", "machines": {}}


def load_digest(home: Path) -> dict:
    path = digest_path(home)
    if not path.exists():
        return empty_digest()
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_digest()
    if not isinstance(doc, dict):
        return empty_digest()
    doc.setdefault("v", 1)
    doc.setdefault("machines", {})
    return doc


def save_digest(home: Path, doc: dict) -> None:
    path = digest_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso_since(raw: str) -> str | None:
    s = (raw or "").strip()
    if not s:
        return None
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        s = s + "T00:00:00Z"
    try:
        if s.endswith("Z"):
            t = datetime.fromisoformat(s.replace("Z", "+00:00"))
        else:
            t = datetime.fromisoformat(s)
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
        return t.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except ValueError:
        return None


def _parse_pcent(raw: str) -> int | None:
    s = (raw or "").strip().rstrip("%")
    try:
        n = int(s)
    except ValueError:
        return None
    if 0 <= n <= 100:
        return n
    return None


@dataclass
class ReportOutcome:
    ok: bool
    err: str | None = None
    help_text: str | None = None
    speak_channel: str | None = None
    echo_raw: bool = False


def _machine_entry(doc: dict, machine_id: str, sender_nick: str) -> dict:
    machines = doc.setdefault("machines", {})
    mid = normalize_machine_id(machine_id) or machine_id
    ent = machines.get(mid)
    if not isinstance(ent, dict):
        ent = {"nick": sender_nick or nick_for_machine(machines, mid)}
        machines[mid] = ent
    if sender_nick:
        ent["nick"] = sender_nick
    ent.setdefault("pcent", {})
    return ent


def apply_report(home: Path, sender_nick: str, briefer_nick: str, body: str) -> ReportOutcome:
    if looks_like_secret(body):
        return ReportOutcome(ok=False, err="ERR report refused (secret-like token)")

    text = (body or "").strip()
    parts = text.split()
    if not parts or parts[0].lower() != REPORT_CMD:
        return ReportOutcome(ok=False, err="ERR report bad command")
    if len(parts) < 2:
        return ReportOutcome(ok=False, err="ERR report missing verb")

    verb = parts[1].lower()
    if verb in ("?", "help"):
        return ReportOutcome(ok=True, help_text=HELP_TEXT)

    doc = load_digest(home)
    doc["briefer"] = briefer_nick
    doc["ts"] = _utc_now_iso()

    if verb == "task":
        if len(parts) < 4:
            return ReportOutcome(ok=False, err="ERR report TASK needs START|STOP")
        state = parts[2].upper()
        if state not in ("START", "STOP"):
            return ReportOutcome(ok=False, err="ERR report TASK needs START|STOP")
        if len(parts) < 8:
            return ReportOutcome(ok=False, err="ERR report TASK missing fields")
        repo, sha, model = parts[3], parts[4], parts[5]
        run_time = parts[-1]
        desc = " ".join(parts[6:-1])
        if not SHA_RE.match(sha):
            return ReportOutcome(ok=False, err="ERR report bad sha")
        if not repo or not model or not desc or not run_time:
            return ReportOutcome(ok=False, err="ERR report TASK missing fields")
        mid = machine_from_nick(sender_nick)
        if not mid:
            return ReportOutcome(ok=False, err="ERR report unknown sender machine")
        ent = _machine_entry(doc, mid, sender_nick)
        ent["task"] = {
            "state": state,
            "repo": repo,
            "sha": sha if sha != "-" else "-",
            "model": model,
            "description": desc,
            "run_time": run_time,
        }
        save_digest(home, doc)
        mid_disp = "dev1" if mid == "ce-priority-dev1" else mid
        if state == "START":
            speak = f"{mid_disp} started {repo} ({run_time})."
        else:
            speak = f"{mid_disp} stopped {repo}."
        return ReportOutcome(ok=True, speak_channel=speak)

    if verb == "pcent":
        if len(parts) < 5:
            return ReportOutcome(ok=False, err="ERR report PCENT needs machine source n%")
        mid = normalize_machine_id(parts[2])
        if not mid:
            return ReportOutcome(ok=False, err="ERR report bad machine id")
        source = parts[3].strip()
        if not source or "=" in source:
            return ReportOutcome(ok=False, err="ERR report bad PCENT source")
        pct = _parse_pcent(parts[4])
        if pct is None:
            return ReportOutcome(ok=False, err="ERR report bad PCENT percent")
        ent = _machine_entry(doc, mid, nick_for_machine(doc.get("machines") or {}, mid))
        pcent = ent.setdefault("pcent", {})
        if isinstance(pcent, dict) and pcent.get(source) == pct:
            save_digest(home, doc)
            return ReportOutcome(ok=True)
        if isinstance(pcent, dict):
            pcent[source] = pct
        save_digest(home, doc)
        return ReportOutcome(ok=True)

    if verb == "uptime":
        if len(parts) < 3:
            return ReportOutcome(ok=False, err="ERR report UPTIME needs since-iso")
        since = _parse_iso_since(parts[2])
        if not since:
            return ReportOutcome(ok=False, err="ERR report bad UPTIME since")
        mid = machine_from_nick(sender_nick)
        if not mid:
            return ReportOutcome(ok=False, err="ERR report unknown sender machine")
        ent = _machine_entry(doc, mid, sender_nick)
        ent["uptime_since"] = since
        save_digest(home, doc)
        return ReportOutcome(ok=True)

    return ReportOutcome(ok=False, err="ERR report unknown verb")


def build_digest_object(home: Path, briefer_nick: str) -> dict:
    doc = load_digest(home)
    out = {
        "v": int(doc.get("v") or 1),
        "ts": str(doc.get("ts") or _utc_now_iso()),
        "briefer": briefer_nick or str(doc.get("briefer") or ""),
        "machines": doc.get("machines") if isinstance(doc.get("machines"), dict) else {},
    }
    return out


def format_digest_whisper_lines(home: Path, briefer_nick: str) -> list[str]:
    obj = build_digest_object(home, briefer_nick)
    raw = json.dumps(obj, separators=(",", ":"), sort_keys=True)
    if len(raw) <= MAX_DIGEST_LINE:
        return [raw]
    chunks: list[str] = []
    n = (len(raw) + MAX_DIGEST_LINE - 1) // MAX_DIGEST_LINE
    for i in range(n):
        piece = raw[i * MAX_DIGEST_LINE : (i + 1) * MAX_DIGEST_LINE]
        chunks.append(f"{DIGEST_PREFIX}{i + 1}/{n} {piece}")
    return chunks
