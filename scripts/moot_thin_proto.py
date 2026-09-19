#!/usr/bin/env python3
"""Mode 3 thin-client protocol helpers. Offline. No sockets.

Golden spec for airc-moot-thin.exe: DUMB v1 jobs + moot JOIN + --operators.
Exec/jail rules reuse scripts/dumb_agent.py so Mode 2 behaviour stays the reference.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import dumb_agent
import seal

MSGID_RE = re.compile(r"^[a-fA-F0-9]{16}$")


@dataclass
class ThinConfig:
    nick: str = ""
    channel: str = ""
    moot_id: str = ""
    home: str = ""
    allow_path: str = ""
    operators: str = ""
    key_path: str = ""
    host: str = "127.0.0.1"
    port: int = 6697
    hello: str = ""
    realname: str = "airc-moot-thin"
    allow_bin_extra: str = ""
    from_nick: str = ""


def _norm_key(k: str) -> str:
    return re.sub(r"[-_]", "", k.strip().lower())


def parse_ini(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(";") or line.startswith("["):
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[_norm_key(k)] = v.strip()
    return out


def parse_argv(argv: list[str]) -> dict[str, str | bool]:
    out: dict[str, str | bool] = {}
    i = 0
    flags = {"help", "version", "selftest", "offline", "once"}
    while i < len(argv):
        a = argv[i]
        if a in ("-h", "--help"):
            out["help"] = True
            i += 1
            continue
        if a.startswith("--") and a[2:] in flags:
            out[a[2:]] = True
            i += 1
            continue
        if a.startswith("--"):
            key = _norm_key(a[2:])
            val = argv[i + 1] if i + 1 < len(argv) else ""
            if i + 1 < len(argv):
                i += 1
            out[key] = val
        i += 1
    return out


_FIELD = {
    "nick": "nick",
    "channel": "channel",
    "moot": "moot_id",
    "mootid": "moot_id",
    "id": "moot_id",
    "home": "home",
    "allowpath": "allow_path",
    "operators": "operators",
    "key": "key_path",
    "keypath": "key_path",
    "host": "host",
    "hello": "hello",
    "realname": "realname",
    "fromnick": "from_nick",
    "allowbin": "allow_bin_extra",
}


def apply_kv(cfg: ThinConfig, kv: dict) -> ThinConfig:
    for k, v in kv.items():
        if k == "port":
            cfg.port = int(v)
            continue
        attr = _FIELD.get(k)
        if attr:
            setattr(cfg, attr, str(v))
    return cfg


def merge_config(ini: dict | None, argv: dict | None) -> ThinConfig:
    cfg = ThinConfig()
    if ini:
        apply_kv(cfg, ini)
    if argv:
        apply_kv(cfg, {k: v for k, v in argv.items() if not isinstance(v, bool)})
    return cfg


def operators_set(raw: str) -> set[str]:
    return {x.strip() for x in (raw or "").split(",") if x.strip()}


def require_operators(raw: str) -> set[str]:
    ops = operators_set(raw)
    if not ops:
        raise ValueError("installer MUST refuse empty --operators")
    return ops


def validate_config(cfg: ThinConfig) -> None:
    if not cfg.nick or not seal.NICK_RE.match(cfg.nick):
        raise ValueError("invalid --nick")
    if not cfg.channel.startswith("#") or "|" in cfg.channel:
        raise ValueError("invalid --channel")
    if not MSGID_RE.match(cfg.moot_id):
        raise ValueError("invalid --moot (16 hex)")
    if not cfg.home:
        raise ValueError("missing --home")
    if not cfg.allow_path:
        raise ValueError("missing --allow-path")
    require_operators(cfg.operators)


def moot_join_line(moot_id: str) -> str:
    return f"MOOT v1 JOIN {moot_id}"


def capa_line(nick: str, jail: str, psk: bool) -> str:
    return (
        f"CAPA v1 dumb nick={nick} verbs=ping,sysinfo,exec,get,put "
        f"psk={1 if psk else 0} agpk=0 jail={jail}"
    )


def run_job(
    job: dict,
    *,
    operators: set[str],
    from_nick: str,
    allow_path: Path,
    home: Path | None = None,
    allow_bin: set[str] | None = None,
) -> dict:
    return dumb_agent.run_job(
        job,
        operators=operators,
        from_nick=from_nick,
        allow_path=allow_path,
        allow_bin=allow_bin or set(dumb_agent.DEFAULT_BINS),
        home=home,
    )


def emit_result_on_wire(from_nick: str, operators: set[str]) -> bool:
    """Unknown operator: no exec, no result ciphertext on the wire."""
    return from_nick.lower() in {x.lower() for x in operators}
