#!/usr/bin/env python3
"""Shop-channel digest + !bobiverse reader (issue #46). !report write path scrubbed."""
from __future__ import annotations

import copy
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import bobstat
import bobtalk

REPORT_CMD = "!report"
REPORT_GONE = "ERR report gone — use callback or !bobiverse"
NO_MACHINE = "ERR no such machine"
DIGEST_PREFIX = "BOB DIGEST v1 "
MAX_DIGEST_LINE = 350
FLEET_CHANNEL = "#bobiverse"
ACTION_COOLDOWN_S = 30.0
DISCONNECT_DEDUPE_S = 30.0
ID_ALIASES = {"dev1": "ce-priority-dev1", "ce-priority-dev1": "ce-priority-dev1"}

NICK_TO_MACHINE: dict[str, str] = {
    "bob-flamingo": "flamingo",
    "bob-marchhare": "marchhare",
    "bob-ionos": "ionos",
    "bob-dev1": "ce-priority-dev1",
}

SHORT_ID: dict[str, str] = {
    "flamingo": "fl",
    "marchhare": "mh",
    "ionos": "io",
    "ce-priority-dev1": "d1",
}
SHORT_TO_MACHINE = {v: k for k, v in SHORT_ID.items()}
FLEET_MACHINE_IDS = ("flamingo", "marchhare", "ionos", "ce-priority-dev1")
_MERGE_PEER_FIELDS = (
    "weekly",
    "cursor_label",
    "jobs",
    "repo",
    "sha",
    "model",
    "fuel",
    "lastSeen",
    "running",
    "queued",
    "period_end",
    "reset",
    "kind",
    "cur",
)
_TRAY_MACHINE_EXPORT_KEYS = (
    "id",
    "nick",
    "shop",
    "online",
    "status",
    "working_on",
    "workers",
    "weekly",
    "period_end",
    "reset",
    "lastSeen",
    "running",
    "queued",
    "jobs",
    "pcent",
    "uptime_since",
    "fuel",
    "model",
    "repo",
    "sha",
    "cursor_label",
    "kind",
    "cur",
)
WORKER_NICK_RE = re.compile(r"^w-([a-z0-9]+)-(\d+)_?$", re.I)

HELP_TEXT = (
    "!bobiverse          JSON digest (whisper)\n"
    "!bobiverse <id>     one machine\n"
    "!bobiverse ?        this text\n"
    "write: POST reportUrl (no !report)"
)

_SECRET_MARKERS = (
    "password=",
    "xai_api_key=",
    "connect.password",
    "x-bob-secret",
    "bob_report_secret",
    "report.secret",
    "psk=",
    "pin=",
)

_DISCONNECT_DEDUPE: dict[tuple[str, str], float] = {}

CC_SHOP = "shop"
CC_QUERY = "query"
WORKING_ON_PREFIX = "This is what I'm working on: "
WORKING_ON_SHOP_SEP = ": " + WORKING_ON_PREFIX


def looks_like_secret(text: str) -> bool:
    lower = (text or "").lower()
    return any(m in lower for m in _SECRET_MARKERS)


def reset_dedupe() -> None:
    _DISCONNECT_DEDUPE.clear()


def normalize_machine_id(raw: str) -> str | None:
    mid = str(raw or "").strip().lower().lstrip("#")
    if not mid or mid == "nope":
        return None
    mid = ID_ALIASES.get(mid, mid)
    if not bobstat.ID_RE.match(mid):
        return None
    if mid not in SHORT_ID and mid not in ID_ALIASES:
        # accept registry ids even if extra, as long as they look like ids
        if mid not in FLEET_MACHINE_IDS:
            return mid if bobstat.ID_RE.match(mid) else None
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


def shop_channel(machine_id: str) -> str:
    mid = normalize_machine_id(machine_id)
    if not mid:
        raise ValueError("bad machine id")
    return f"#{mid}"


def normalize_channel(raw: str) -> str:
    c = (raw or "").strip()
    if not c:
        return c
    if not c.startswith("#"):
        c = "#" + c
    mid = normalize_machine_id(c[1:])
    if mid:
        return f"#{mid}"
    return c


def worker_key(machine_id: str, pid: int | str) -> str:
    mid = normalize_machine_id(machine_id)
    if not mid:
        raise ValueError("bad machine id")
    return f"{mid}:{int(pid)}"


def worker_nick(machine_id: str, pid: int | str) -> str:
    mid = normalize_machine_id(machine_id)
    if not mid or mid not in SHORT_ID:
        raise ValueError("bad machine id")
    return f"w-{SHORT_ID[mid]}-{int(pid)}"


def parse_worker_nick(nick: str) -> tuple[str, str] | None:
    n = (nick or "").strip()
    m = WORKER_NICK_RE.match(n)
    if not m:
        return None
    short = m.group(1).lower()
    pid = m.group(2)
    mid = SHORT_TO_MACHINE.get(short)
    if not mid:
        return None
    return mid, pid


def worker_home(base: Path | str, machine_id: str, pid: int | str) -> Path:
    mid = normalize_machine_id(machine_id)
    if not mid:
        raise ValueError("bad machine id")
    return Path(base) / "workers" / mid / str(int(pid))


def parse_channel_list(raw: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for part in (raw or "").split(","):
        c = part.strip()
        if not c:
            continue
        c = normalize_channel(c)
        if "|" in c:
            raise ValueError("channel must not contain |")
        key = c.lower()
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def channels_for_nick(nick: str, requested: str) -> list[str]:
    """bob-* → fleet + shop; w-* → shop only; others keep --channel."""
    req = parse_channel_list(requested)
    worker = parse_worker_nick(nick)
    if worker:
        return [shop_channel(worker[0])]
    mid = machine_from_nick(nick)
    if mid:
        shop = shop_channel(mid)
        return [FLEET_CHANNEL, shop]
    return req


def parse_report_command(body: str) -> bool:
    text = (body or "").strip()
    if not text:
        return False
    return text.split(None, 1)[0].lower() == REPORT_CMD


def parse_bobiverse_query(body: str) -> tuple[str, str | None] | None:
    text = (body or "").strip()
    if not text:
        return None
    parts = text.split()
    if parts[0].lower() != bobtalk.BOBIVERSE_CMD:
        return None
    if len(parts) == 1:
        return ("full", None)
    rest = parts[1]
    if rest.lower() in ("?", "help"):
        return ("help", None)
    mid = normalize_machine_id(rest)
    return ("machine", mid or rest.lower())


def digest_path(home: Path) -> Path:
    return Path(home) / "digest.json"


def fleet_digest_home(home: Path) -> Path:
    """Digest root when worker home is .../workers/<machine>/<pid>."""
    p = Path(home)
    if p.name.isdigit() and p.parent.parent.name == "workers":
        return p.parent.parent.parent
    return p


def _empty_machine(machine_id: str) -> dict:
    mid = normalize_machine_id(machine_id) or machine_id
    return {
        "id": mid,
        "nick": nick_for_machine({}, mid),
        "shop": shop_channel(mid) if normalize_machine_id(mid) else f"#{mid}",
        "online": False,
        "status": "I am offline",
        "working_on": "",
        "workers": {},
    }


def empty_digest() -> dict:
    return {
        "v": 1,
        "ts": "",
        "briefer": "",
        "machines": {mid: _empty_machine(mid) for mid in FLEET_MACHINE_IDS},
        "events": [],
    }


def _coerce_worker(mid: str, pid: str, raw: object) -> dict:
    ent = raw if isinstance(raw, dict) else {}
    try:
        pid_s = str(int(str(pid)))
    except ValueError:
        pid_s = str(pid)
    nick = str(ent.get("nick") or "")
    if not nick:
        try:
            nick = worker_nick(mid, pid_s)
        except ValueError:
            nick = f"w-xx-{pid_s}"
    return {
        "pid": pid_s,
        "key": str(ent.get("key") or worker_key(mid, pid_s) if normalize_machine_id(mid) else f"{mid}:{pid_s}"),
        "nick": nick,
        "kind": str(ent.get("kind") or ""),
        "state": str(ent.get("state") or "running"),
        "working_on": str(ent.get("working_on") or ""),
    }


def _coerce_workers(mid: str, raw: object) -> dict:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict] = {}
    for pid, ent in raw.items():
        try:
            pid_s = str(int(str(pid)))
        except ValueError:
            continue
        out[pid_s] = _coerce_worker(mid, pid_s, ent)
    return out


def _coerce_machine(mid: str, raw: object) -> dict:
    base = _empty_machine(mid)
    if not isinstance(raw, dict):
        return base
    online = bool(raw.get("online", False))
    status = str(raw.get("status") or ("I am online" if online else "I am offline"))
    base.update(
        {
            "nick": str(raw.get("nick") or base["nick"]),
            "shop": str(raw.get("shop") or base["shop"]),
            "online": online,
            "status": status,
            "working_on": str(raw.get("working_on") or ""),
            "workers": _coerce_workers(mid, raw.get("workers")),
        }
    )
    if isinstance(raw.get("pcent"), dict):
        base["pcent"] = raw["pcent"]
    if raw.get("uptime_since"):
        base["uptime_since"] = str(raw["uptime_since"])
    for key in _MERGE_PEER_FIELDS:
        if key in raw and raw[key] is not None:
            base[key] = raw[key]
    if "running" in base:
        try:
            base["running"] = int(base["running"])
        except (TypeError, ValueError):
            base["running"] = 0
    if "queued" in base:
        try:
            base["queued"] = int(base["queued"])
        except (TypeError, ValueError):
            base["queued"] = 0
    return base


def _ensure_seats(doc: dict) -> dict:
    machines = doc.setdefault("machines", {})
    if not isinstance(machines, dict):
        machines = {}
        doc["machines"] = machines
    for mid in FLEET_MACHINE_IDS:
        machines[mid] = _coerce_machine(mid, machines.get(mid))
    extra = [k for k in list(machines) if k not in FLEET_MACHINE_IDS]
    for mid in extra:
        machines[mid] = _coerce_machine(mid, machines.get(mid))
    doc.setdefault("v", 1)
    doc.setdefault("events", [])
    if not isinstance(doc["events"], list):
        doc["events"] = []
    pools = doc.get("cursor_pools")
    if pools is not None and not isinstance(pools, list):
        doc["cursor_pools"] = []
    return doc


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
    return _ensure_seats(doc)


def save_digest(home: Path, doc: dict) -> None:
    path = digest_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _note_event(doc: dict, kind: str, **fields: object) -> None:
    ev = {"ts": _utc_now_iso(), "kind": kind}
    ev.update(fields)
    events = doc.setdefault("events", [])
    if not isinstance(events, list):
        events = []
    events.append(ev)
    doc["events"] = events[-20:]


def _roll_working_on(ent: dict) -> None:
    workers = ent.get("workers") if isinstance(ent.get("workers"), dict) else {}
    for w in workers.values():
        text = str((w or {}).get("working_on") or "").strip()
        if text:
            ent["working_on"] = text
            return
    ent["working_on"] = ""


def _machine_entry(doc: dict, machine_id: str) -> dict:
    mid = normalize_machine_id(machine_id) or machine_id
    machines = doc.setdefault("machines", {})
    ent = _coerce_machine(mid, machines.get(mid))
    machines[mid] = ent
    return ent


def _set_online(ent: dict, online: bool) -> None:
    ent["online"] = online
    ent["status"] = "I am online" if online else "I am offline"
    if not online:
        ent["working_on"] = ""
        ent["workers"] = {}


@dataclass
class ReportOutcome:
    ok: bool
    err: str | None = None
    help_text: str | None = None
    speak_channel: str | None = None
    echo_raw: bool = False


@dataclass
class PresenceOutcome:
    ok: bool
    err: str | None = None
    actions: list[str] = field(default_factory=list)
    shop_closed: bool = False
    deleted_pid: str | None = None
    machine_id: str | None = None


@dataclass
class CallbackOutcome:
    ok: bool
    err: str = ""
    actions: list[str] = field(default_factory=list)
    changed: bool = True


CHAIR_NICK_ENV = "AGENTIC_IRC_CHAIR_NICK"


def digest_chair_nick(home: Path) -> str | None:
    """Dedicated digest chair (issue #73). Env wins over digest.json chairNick."""
    env = (os.environ.get(CHAIR_NICK_ENV) or "").strip()
    if env:
        return env
    doc = load_digest(home)
    raw = str(doc.get("chairNick") or doc.get("chair_nick") or "").strip()
    return raw or None


def chair_mode_active(home: Path) -> bool:
    return bool(digest_chair_nick(home))


def persist_chair_nick(home: Path, nick: str) -> None:
    """Write digest chair identity to shared digest.json (issue #73 / #78)."""
    n = (nick or "").strip()
    if not n:
        return
    root = fleet_digest_home(Path(home))
    doc = load_digest(root)
    if str(doc.get("chairNick") or "") == n:
        return
    doc["chairNick"] = n
    save_digest(root, doc)


def _fleet_spam_privmsg_body(body: str) -> bool:
    """Outbox / channel lines that must not hit #bobiverse when chair mode is on."""
    raw = (body or "").strip()
    if not raw:
        return False
    low = raw.lower().replace("\x01", " ")
    if low.startswith("bob digest v1"):
        return True
    if low.startswith("bob tray v1"):
        return True
    if "i am offline" in low or "i am online" in low:
        return True
    if "working on" in low:
        return True
    if " is on " in low and (" now." in low or " now" in low):
        return True
    if low.startswith("action ") or " action " in low:
        return True
    if " here. weekly=" in low:
        return True
    return False


def outbox_line_spam_for_fleet_channel(line: str, *, default_channel: str = FLEET_CHANNEL) -> bool:
    """True if line must be dropped (not sent) to #bobiverse under chair mode."""
    text = (line or "").strip()
    if not text:
        return False
    to_fleet = default_channel.lower() == FLEET_CHANNEL.lower()
    body = text
    if text.upper().startswith("PRIVMSG "):
        rest = text[8:]
        target, _, tail = rest.partition(" ")
        to_fleet = target.lstrip(":").lower() == FLEET_CHANNEL.lower()
        body = tail[1:] if tail.startswith(":") else (text.split(" :", 1)[1] if " :" in text else text)
    if not to_fleet:
        return False
    return _fleet_spam_privmsg_body(body)


def _machine_fingerprint(ent: dict) -> str:
    view = {
        "online": ent.get("online"),
        "status": ent.get("status"),
        "working_on": ent.get("working_on"),
        "pcent": ent.get("pcent"),
        "uptime_since": ent.get("uptime_since"),
        "workers": ent.get("workers"),
    }
    for key in _MERGE_PEER_FIELDS:
        if key in ent:
            view[key] = ent.get(key)
    return json.dumps(view, sort_keys=True, separators=(",", ":"))


def _merge_worker_on_ent(
    ent: dict, mid: str, pid_s: str, working_on: str, kind: str = "grok"
) -> list[str]:
    text = (working_on or "").strip()
    if not text:
        return []
    if looks_like_secret(text) or looks_like_secret(kind):
        return []
    workers = ent.setdefault("workers", {})
    prev = workers.get(pid_s) or {}
    prev_wo = str(prev.get("working_on") or "").strip()
    if prev_wo == text and prev:
        return []
    ent["online"] = True
    ent["status"] = "I am online"
    w = _coerce_worker(
        mid,
        pid_s,
        {
            **prev,
            "kind": kind or prev.get("kind") or "grok",
            "state": prev.get("state") or "running",
            "working_on": text,
            "nick": prev.get("nick") or worker_nick(mid, pid_s),
            "key": worker_key(mid, pid_s),
        },
    )
    workers[pid_s] = w
    _roll_working_on(ent)
    return [f"'s pid {pid_s} on {mid} is working on {text}"]


def _apply_merge_payload(doc: dict, mid: str, payload: dict) -> list[str]:
    """Mutate digest doc for one machine merge; return new English actions."""
    actions: list[str] = []
    pid_raw = payload.get("pid")
    ent = _machine_entry(doc, mid)
    if pid_raw is not None and str(pid_raw) != "" and "working_on" in payload:
        try:
            pid_s = str(int(str(pid_raw)))
        except ValueError:
            return []
        kind = str(payload.get("kind") or "grok")
        actions.extend(_merge_worker_on_ent(ent, mid, pid_s, str(payload.get("working_on") or ""), kind=kind))
    if "online" in payload:
        ent["online"] = bool(payload["online"])
        ent["status"] = "I am online" if ent["online"] else "I am offline"
    if payload.get("status"):
        ent["status"] = str(payload["status"])
    if "pcent" in payload and isinstance(payload["pcent"], dict):
        ent["pcent"] = payload["pcent"]
    if payload.get("uptime_since"):
        ent["uptime_since"] = str(payload["uptime_since"])
    if pid_raw is not None and str(pid_raw) != "":
        try:
            pid_s = str(int(str(pid_raw)))
        except ValueError:
            return actions
        if "working_on" not in payload:
            wo = str(payload.get("working_on") or "")
            if looks_like_secret(wo):
                return actions
            workers = ent.setdefault("workers", {})
            prev = workers.get(pid_s) or {}
            workers[pid_s] = _coerce_worker(
                mid,
                pid_s,
                {
                    **prev,
                    "kind": payload.get("kind", prev.get("kind") or ""),
                    "state": payload.get("state", prev.get("state") or "running"),
                    "working_on": prev.get("working_on") or "",
                    "nick": payload.get("nick") or prev.get("nick") or worker_nick(mid, pid_s),
                },
            )
            _roll_working_on(ent)
    elif "working_on" in payload and (pid_raw is None or str(pid_raw) == ""):
        ent["working_on"] = str(payload.get("working_on") or "")
    for key in _MERGE_PEER_FIELDS:
        if key not in payload or payload[key] is None:
            continue
        val = payload[key]
        if key == "jobs" and not isinstance(val, list):
            continue
        ent[key] = val
    if "running" in ent:
        try:
            ent["running"] = int(ent["running"])
        except (TypeError, ValueError):
            ent["running"] = 0
    if "queued" in ent:
        try:
            ent["queued"] = int(ent["queued"])
        except (TypeError, ValueError):
            ent["queued"] = 0
    return actions


def apply_report(home: Path, sender_nick: str, briefer_nick: str, body: str) -> ReportOutcome:
    """Scrubbed: never ingest !report. Secret-shaped lines are dropped."""
    del home, sender_nick, briefer_nick
    if looks_like_secret(body):
        return ReportOutcome(ok=False, err="ERR report refused (secret-like token)")
    return ReportOutcome(ok=False, err=REPORT_GONE)


def merge_worker_working_on(
    home: Path,
    machine_id: str,
    pid: int | str,
    working_on: str,
    briefer_nick: str = "",
    kind: str = "grok",
) -> PresenceOutcome:
    text = (working_on or "").strip()
    if not text:
        return PresenceOutcome(ok=False, err="working_on required")
    if looks_like_secret(text) or looks_like_secret(kind):
        return PresenceOutcome(ok=False, err="secret")
    mid = normalize_machine_id(machine_id)
    if not mid:
        return PresenceOutcome(ok=False, err="bad machine")
    try:
        pid_s = str(int(str(pid)))
    except ValueError:
        return PresenceOutcome(ok=False, err="bad pid")
    doc = load_digest(home)
    if briefer_nick:
        doc["briefer"] = briefer_nick
    doc["ts"] = _utc_now_iso()
    ent = _machine_entry(doc, mid)
    workers = ent.setdefault("workers", {})
    prev = workers.get(pid_s) or {}
    prev_wo = str(prev.get("working_on") or "").strip()
    if prev_wo == text and prev:
        return PresenceOutcome(ok=True, machine_id=mid)
    ent["online"] = True
    ent["status"] = "I am online"
    w = _coerce_worker(
        mid,
        pid_s,
        {
            **prev,
            "kind": kind or prev.get("kind") or "grok",
            "state": prev.get("state") or "running",
            "working_on": text,
            "nick": prev.get("nick") or worker_nick(mid, pid_s),
            "key": worker_key(mid, pid_s),
        },
    )
    workers[pid_s] = w
    _roll_working_on(ent)
    _note_event(doc, "worker-start" if not prev else "working_on", machine=mid, pid=pid_s, working_on=text)
    save_digest(home, doc)
    action = f"'s pid {pid_s} on {mid} is working on {text}"
    return PresenceOutcome(ok=True, actions=[action], machine_id=mid)


def start_worker(
    home: Path,
    machine_id: str,
    pid: int | str,
    working_on: str,
    kind: str = "grok",
    briefer_nick: str = "",
) -> PresenceOutcome:
    return merge_worker_working_on(home, machine_id, pid, working_on, briefer_nick, kind=kind)


def delete_worker(home: Path, machine_id: str, pid: int | str, briefer_nick: str = "", now: float | None = None) -> PresenceOutcome:
    mid = normalize_machine_id(machine_id)
    if not mid:
        return PresenceOutcome(ok=False, err="bad machine")
    try:
        pid_s = str(int(str(pid)))
    except ValueError:
        return PresenceOutcome(ok=False, err="bad pid")
    import time

    ts = time.time() if now is None else now
    key = (mid, pid_s)
    last = _DISCONNECT_DEDUPE.get(key, 0.0)
    if ts - last < DISCONNECT_DEDUPE_S:
        return PresenceOutcome(ok=True, deleted_pid=pid_s, machine_id=mid)
    _DISCONNECT_DEDUPE[key] = ts
    doc = load_digest(home)
    if briefer_nick:
        doc["briefer"] = briefer_nick
    doc["ts"] = _utc_now_iso()
    ent = _machine_entry(doc, mid)
    workers = ent.setdefault("workers", {})
    gone = workers.pop(pid_s, None)
    _roll_working_on(ent)
    if gone is not None:
        _note_event(doc, "worker-delete", machine=mid, pid=pid_s)
        save_digest(home, doc)
        nick = str(gone.get("nick") or worker_nick(mid, pid_s))
        shop = ent.get("shop") or shop_channel(mid)
        action = f"sees {nick} drop from {shop} (pid {pid_s})"
        return PresenceOutcome(ok=True, actions=[action], deleted_pid=pid_s, machine_id=mid)
    save_digest(home, doc)
    return PresenceOutcome(ok=True, deleted_pid=pid_s, machine_id=mid)


def shop_down(home: Path, machine_id: str, briefer_nick: str = "") -> PresenceOutcome:
    mid = normalize_machine_id(machine_id)
    if not mid:
        return PresenceOutcome(ok=False, err="bad machine")
    doc = load_digest(home)
    if briefer_nick:
        doc["briefer"] = briefer_nick
    doc["ts"] = _utc_now_iso()
    ent = _machine_entry(doc, mid)
    nick = str(ent.get("nick") or nick_for_machine({}, mid))
    shop = ent.get("shop") or shop_channel(mid)
    _set_online(ent, False)
    _note_event(doc, "shop-down", machine=mid)
    save_digest(home, doc)
    action = f"lost {nick} — {shop} closed"
    return PresenceOutcome(ok=True, actions=[action], shop_closed=True, machine_id=mid)


def apply_join(home: Path, nick: str, channel: str, briefer_nick: str = "") -> PresenceOutcome:
    ch = normalize_channel(channel)
    worker = parse_worker_nick(nick)
    if worker:
        mid, pid = worker
        shop = shop_channel(mid)
        if ch.lower() != shop.lower():
            return PresenceOutcome(ok=True, machine_id=mid)
        doc = load_digest(home)
        if briefer_nick:
            doc["briefer"] = briefer_nick
        doc["ts"] = _utc_now_iso()
        ent = _machine_entry(doc, mid)
        workers = ent.setdefault("workers", {})
        if pid not in workers:
            workers[pid] = _coerce_worker(mid, pid, {"state": "joined", "nick": worker_nick(mid, pid)})
            _note_event(doc, "worker-join", machine=mid, pid=pid)
            save_digest(home, doc)
        return PresenceOutcome(ok=True, machine_id=mid)
    mid = machine_from_nick(nick)
    if not mid:
        return PresenceOutcome(ok=True)
    shop = shop_channel(mid)
    if ch.lower() not in (FLEET_CHANNEL, shop.lower()):
        return PresenceOutcome(ok=True, machine_id=mid)
    doc = load_digest(home)
    if briefer_nick:
        doc["briefer"] = briefer_nick
    doc["ts"] = _utc_now_iso()
    ent = _machine_entry(doc, mid)
    ent["nick"] = (nick or "").strip() or ent["nick"]
    was_offline = not ent.get("online")
    ent["online"] = True
    ent["status"] = "I am online"
    if was_offline:
        ent["working_on"] = ""
        _note_event(doc, "machine-join", machine=mid)
    save_digest(home, doc)
    return PresenceOutcome(ok=True, machine_id=mid)


def apply_part(home: Path, nick: str, channel: str, briefer_nick: str = "") -> PresenceOutcome:
    ch = normalize_channel(channel)
    worker = parse_worker_nick(nick)
    if worker:
        mid, pid = worker
        if ch.lower() == shop_channel(mid).lower():
            return delete_worker(home, mid, pid, briefer_nick)
        return PresenceOutcome(ok=True, machine_id=mid)
    mid = machine_from_nick(nick)
    if mid and ch.lower() == shop_channel(mid).lower():
        return shop_down(home, mid, briefer_nick)
    return PresenceOutcome(ok=True, machine_id=mid)


def apply_quit(home: Path, nick: str, briefer_nick: str = "") -> PresenceOutcome:
    worker = parse_worker_nick(nick)
    if worker:
        mid, pid = worker
        return delete_worker(home, mid, pid, briefer_nick)
    mid = machine_from_nick(nick)
    if mid:
        return shop_down(home, mid, briefer_nick)
    return PresenceOutcome(ok=True)


def apply_callback(home: Path, payload: dict, briefer_nick: str = "") -> CallbackOutcome:
    if not isinstance(payload, dict):
        return CallbackOutcome(ok=False, err="malformed")
    if any(k.lower() in ("secret", "x-bob-secret", "password") for k in payload):
        return CallbackOutcome(ok=False, err="secret")
    blob = json.dumps(payload, separators=(",", ":"))
    if looks_like_secret(blob):
        return CallbackOutcome(ok=False, err="secret")
    op = str(payload.get("op") or "").strip().lower()
    mid = normalize_machine_id(str(payload.get("machine") or payload.get("id") or ""))
    actions: list[str] = []
    if op == "merge":
        if not mid:
            return CallbackOutcome(ok=False, err="bad machine")
        pid_raw = payload.get("pid")
        if pid_raw is not None and str(pid_raw) != "" and "working_on" in payload:
            try:
                str(int(str(pid_raw)))
            except ValueError:
                return CallbackOutcome(ok=False, err="bad pid")
            text = str(payload.get("working_on") or "").strip()
            if not text:
                return CallbackOutcome(ok=False, err="working_on required")
            if looks_like_secret(text):
                return CallbackOutcome(ok=False, err="secret")
        doc = load_digest(home)
        ent_before = copy.deepcopy(_machine_entry(doc, mid))
        fp_before = _machine_fingerprint(ent_before)
        pools_before = copy.deepcopy(doc.get("cursor_pools"))
        if isinstance(payload.get("cursor_pools"), list):
            doc["cursor_pools"] = _coerce_cursor_pools(payload["cursor_pools"])
        actions = _apply_merge_payload(doc, mid, payload)
        fp_after = _machine_fingerprint(_machine_entry(doc, mid))
        pools_after = doc.get("cursor_pools")
        if fp_before == fp_after and pools_before == pools_after:
            return CallbackOutcome(ok=True, changed=False, actions=[])
        if briefer_nick:
            doc["briefer"] = briefer_nick
        doc["ts"] = _utc_now_iso()
        _note_event(doc, "merge", machine=mid)
        save_digest(home, doc)
        return CallbackOutcome(ok=True, actions=actions)
    if op == "delete-worker":
        if not mid:
            return CallbackOutcome(ok=False, err="bad machine")
        out = delete_worker(home, mid, payload.get("pid") or "", briefer_nick)
        if out.ok and out.actions:
            actions.extend(out.actions)
        if out.ok:
            return CallbackOutcome(ok=True, actions=actions)
        return CallbackOutcome(ok=False, err=out.err or "bad delete")
    if op == "shop-down":
        if not mid:
            return CallbackOutcome(ok=False, err="bad machine")
        out = shop_down(home, mid, briefer_nick)
        if out.ok and out.actions:
            actions.extend(out.actions)
        if out.ok:
            return CallbackOutcome(ok=True, actions=actions)
        return CallbackOutcome(ok=False, err=out.err or "bad shop-down")
    return CallbackOutcome(ok=False, err="bad op")


def route_cc(kind: str, pm_open: bool) -> frozenset[str]:
    k = (kind or "").strip().lower().replace("-", "_")
    if k in ("secret", "secrets", "secrets_shaped"):
        return frozenset()
    if k in ("thinking", "tool", "tool_xscr", "trace", "transcript"):
        return frozenset({CC_QUERY}) if pm_open else frozenset()
    if k in ("assistant", "stdout", "visible"):
        dest = {CC_SHOP}
        if pm_open:
            dest.add(CC_QUERY)
        return frozenset(dest)
    if k in ("working_on",):
        return frozenset({CC_SHOP})
    return frozenset()


def working_on_shop_line(nick: str, text: str) -> str:
    return f"{nick}: {WORKING_ON_PREFIX}{text}"


def parse_working_on_shop_line(body: str) -> tuple[str | None, str] | None:
    """Parse shop PRIVMSG body; return (nick or None, job text)."""
    text = (body or "").strip()
    if not text:
        return None
    if WORKING_ON_SHOP_SEP in text:
        left, job = text.split(WORKING_ON_SHOP_SEP, 1)
        nick = left.strip()
        job = job.strip()
        if nick and parse_worker_nick(nick) and job:
            return nick, job
        return None
    if text.startswith(WORKING_ON_PREFIX):
        job = text[len(WORKING_ON_PREFIX) :].strip()
        return (None, job) if job else None
    return None


def ingest_working_on_shop(
    home: Path, sender_nick: str, body: str, briefer_nick: str = ""
) -> PresenceOutcome:
    parsed = parse_working_on_shop_line(body)
    if not parsed:
        return PresenceOutcome(ok=False, err="not working_on")
    nick_in_line, job = parsed
    who = (nick_in_line or sender_nick or "").strip()
    worker = parse_worker_nick(who)
    if not worker:
        return PresenceOutcome(ok=False, err="not worker")
    mid, pid = worker
    out = merge_worker_working_on(home, mid, pid, job, briefer_nick)
    if not out.ok:
        return out
    if out.actions:
        return out
    action = f"'s pid {pid} on {mid} is working on {job.strip()}"
    return PresenceOutcome(ok=True, actions=[action], machine_id=mid)


def split_irc_text(text: str, limit: int = MAX_DIGEST_LINE) -> list[str]:
    raw = (text or "").strip()
    if not raw:
        return []
    if looks_like_secret(raw):
        return []
    if len(raw) <= limit:
        return [raw]
    return [raw[i : i + limit] for i in range(0, len(raw), limit)]


def machine_english(ent: dict) -> str:
    mid = bobtalk.display_id(str(ent.get("id") or "?"))
    if not ent.get("online"):
        return f"{mid}: I am offline"
    workers = ent.get("workers") if isinstance(ent.get("workers"), dict) else {}
    for pid, w in workers.items():
        wo = str((w or {}).get("working_on") or "").strip()
        if wo:
            return f"{mid}: working on {wo} (pid {pid})"
    wo = str(ent.get("working_on") or "").strip()
    if wo:
        return f"{mid}: working on {wo}"
    return f"{mid}: I am online (idle)"


def english_summary_lines(home: Path) -> list[str]:
    doc = load_digest(home)
    lines: list[str] = []
    machines = doc.get("machines") if isinstance(doc.get("machines"), dict) else {}
    for mid in FLEET_MACHINE_IDS:
        ent = machines.get(mid)
        if isinstance(ent, dict):
            lines.append(machine_english(ent))
    return lines


def _normalize_job_entry(raw: object) -> dict | None:
    if not isinstance(raw, dict):
        return None
    repo = str(raw.get("repo") or "").strip()
    state = str(raw.get("state") or "running").strip() or "running"
    entry = {
        "repo": repo,
        "sha": str(raw.get("sha") or "").strip(),
        "model": str(raw.get("model") or "").strip(),
        "description": str(raw.get("description") or raw.get("desc") or "").strip(),
        "state": state,
        "run_time": str(raw.get("run_time") or raw.get("runtime") or "").strip(),
    }
    blob = json.dumps(entry, separators=(",", ":"))
    if looks_like_secret(blob):
        return None
    return entry


def _normalize_jobs_list(raw: object) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw:
        norm = _normalize_job_entry(item)
        if norm is not None:
            out.append(norm)
    return out


def _coerce_cursor_pool(raw: object) -> dict | None:
    if not isinstance(raw, dict):
        return None
    pool_id = str(raw.get("id") or raw.get("seat") or "").strip()
    if not pool_id:
        return None
    label = str(raw.get("label") or "Cursor Models").strip()
    remaining = raw.get("remaining")
    if remaining is None:
        remaining = raw.get("used")
    if remaining is not None:
        try:
            remaining = int(remaining)
        except (TypeError, ValueError):
            remaining = None
    period = raw.get("period_end") or raw.get("reset")
    overage = raw.get("overage")
    if overage is not None:
        overage = str(overage)
    entry = {
        "id": pool_id,
        "seat": str(raw.get("seat") or pool_id),
        "label": label,
        "remaining": remaining,
        "period_end": str(period) if period else None,
        "reset": str(raw.get("reset") or period or "") or None,
        "overage": overage,
    }
    blob = json.dumps(entry, separators=(",", ":"))
    if looks_like_secret(blob):
        return None
    return entry


def _coerce_cursor_pools(raw: object) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for item in raw:
        pool = _coerce_cursor_pool(item)
        if not pool:
            continue
        pid = str(pool.get("id") or "")
        if pid in seen:
            continue
        seen.add(pid)
        out.append(pool)
    return out


def _peer_fill_keys() -> tuple[str, ...]:
    return _MERGE_PEER_FIELDS


def export_machine_for_tray(home: Path, mid: str, ent: dict) -> dict:
    """Tray-complete machine row: digest presence + bob-peers metrics."""
    base = _coerce_machine(mid, ent)
    peer = bobstat.read_peer(home, mid)
    if peer:
        for key in _peer_fill_keys():
            if key not in peer or peer[key] is None or peer[key] == "":
                continue
            if key not in base or base.get(key) in (None, "", [], {}):
                base[key] = peer[key]
    for key in _peer_fill_keys():
        if key in ent and ent[key] is not None and ent[key] != "":
            base[key] = ent[key]
    try:
        base["running"] = int(base.get("running") or 0)
    except (TypeError, ValueError):
        base["running"] = 0
    try:
        base["queued"] = int(base.get("queued") or 0)
    except (TypeError, ValueError):
        base["queued"] = 0
    weekly = base.get("weekly")
    if weekly is not None and weekly != "":
        try:
            base["weekly"] = int(weekly)
        except (TypeError, ValueError):
            base["weekly"] = None
    else:
        base["weekly"] = None
    base["jobs"] = _normalize_jobs_list(base.get("jobs"))
    if base.get("period_end") in (None, ""):
        reset = base.get("reset")
        if reset:
            base["period_end"] = str(reset)
    out: dict = {}
    for key in _TRAY_MACHINE_EXPORT_KEYS:
        if key in base:
            out[key] = base[key]
    out.setdefault("id", mid)
    out.setdefault("nick", nick_for_machine({}, mid))
    out.setdefault("shop", shop_channel(mid))
    out.setdefault("online", False)
    out.setdefault("status", "I am offline" if not out.get("online") else "I am online")
    out.setdefault("working_on", "")
    out.setdefault("workers", {})
    out.setdefault("weekly", None)
    out.setdefault("period_end", None)
    out.setdefault("lastSeen", None)
    out.setdefault("running", 0)
    out.setdefault("queued", 0)
    out.setdefault("jobs", [])
    return out


def build_cursor_pools(doc: dict, machines: dict[str, dict]) -> list[dict]:
    stored = _coerce_cursor_pools(doc.get("cursor_pools"))
    if stored:
        return stored
    pools: list[dict] = []
    seen: set[str] = set()
    for mid in FLEET_MACHINE_IDS:
        ent = machines.get(mid) or {}
        pcent = ent.get("pcent") if isinstance(ent.get("pcent"), dict) else {}
        rem = pcent.get("cursor-models")
        if rem is None:
            rem = pcent.get("cursor_models")
        if rem is None:
            continue
        try:
            remaining = int(rem)
        except (TypeError, ValueError):
            continue
        pid = str(mid)
        if pid in seen:
            continue
        seen.add(pid)
        period = ent.get("period_end") or ent.get("reset")
        pools.append(
            {
                "id": pid,
                "seat": pid,
                "label": str(ent.get("cursor_label") or "Cursor Models"),
                "remaining": remaining,
                "period_end": str(period) if period else None,
                "reset": str(ent.get("reset") or period or "") or None,
                "overage": ent.get("cur"),
            }
        )
    return pools


def build_digest_object(home: Path, briefer_nick: str) -> dict:
    doc = load_digest(home)
    machines = doc.get("machines") if isinstance(doc.get("machines"), dict) else {}
    cleaned: dict[str, dict] = {}
    for mid, ent in machines.items():
        coerced = _coerce_machine(str(mid), ent)
        cleaned[str(coerced["id"])] = coerced
    for mid in FLEET_MACHINE_IDS:
        cleaned.setdefault(mid, _empty_machine(mid))
    exported: dict[str, dict] = {}
    for mid in FLEET_MACHINE_IDS:
        exported[mid] = export_machine_for_tray(home, mid, cleaned[mid])
    chair = (os.environ.get(CHAIR_NICK_ENV) or "").strip() or str(
        doc.get("chairNick") or doc.get("chair_nick") or ""
    ).strip()
    briefer = (briefer_nick or str(doc.get("briefer") or "")).strip()
    return {
        "v": int(doc.get("v") or 1),
        "ts": str(doc.get("ts") or _utc_now_iso()),
        "briefer": briefer,
        "chairNick": chair or briefer,
        "machines": exported,
        "cursor_pools": build_cursor_pools(doc, exported),
    }


def _chunk_json(raw: str) -> list[str]:
    if len(raw) <= MAX_DIGEST_LINE:
        return [raw]
    chunks: list[str] = []
    n = (len(raw) + MAX_DIGEST_LINE - 1) // MAX_DIGEST_LINE
    for i in range(n):
        piece = raw[i * MAX_DIGEST_LINE : (i + 1) * MAX_DIGEST_LINE]
        chunks.append(f"{DIGEST_PREFIX}{i + 1}/{n} {piece}")
    return chunks


def format_digest_whisper_lines(
    home: Path,
    briefer_nick: str,
    form: str = "full",
    machine_id: str | None = None,
    english: bool = True,
) -> list[str]:
    if form == "help":
        return HELP_TEXT.splitlines()
    if form == "machine":
        obj = build_digest_object(home, briefer_nick)
        mid = normalize_machine_id(machine_id or "")
        if not mid or mid not in obj["machines"]:
            return [NO_MACHINE]
        raw = json.dumps(obj["machines"][mid], separators=(",", ":"), sort_keys=True)
        return _chunk_json(raw)
    lines: list[str] = []
    if english:
        lines.extend(english_summary_lines(home))
    raw = json.dumps(build_digest_object(home, briefer_nick), separators=(",", ":"), sort_keys=True)
    lines.extend(_chunk_json(raw))
    return lines
