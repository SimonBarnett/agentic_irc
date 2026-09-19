#!/usr/bin/env python3
"""Mode 3 thin-client protocol helpers. Offline. No sockets.

Golden spec for airc-moot-thin.exe: DUMB v1 jobs + moot JOIN + --operators.
Exec/jail rules reuse scripts/dumb_agent.py so Mode 2 behaviour stays the reference.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import dumb_agent
import seal

MSGID_RE = re.compile(r"^[a-fA-F0-9]{16}$")
PIN_RE = re.compile(r"^[0-9]{6}$")
PAIR_DEFAULT_CHANNEL = "#airc-moot"
PAIR_TTL_S = 600
PIN_WRAP_LABEL = "airc-pin-v1"


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
    pin: str = ""
    chair: bool = False
    pairing: bool = False


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
    flags = {"help", "version", "selftest", "offline", "once", "chair"}
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
    "pin": "pin",
}


def apply_kv(cfg: ThinConfig, kv: dict) -> ThinConfig:
    for k, v in kv.items():
        if k == "port":
            cfg.port = int(v)
            continue
        if k == "chair":
            cfg.chair = bool(v)
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


def pin_ok(pin: str) -> bool:
    return bool(PIN_RE.match(pin or ""))


def sanitize_hostname(host: str) -> str:
    tmp: list[str] = []
    for ch in (host or "").lower():
        if ch.isalnum() or ch in "-_":
            tmp.append(ch)
        elif tmp and tmp[-1] != "-":
            tmp.append("-")
    s = "".join(tmp).strip("-")
    if not s:
        return "thin-box"
    if s[0].isdigit():
        s = "n" + s
    s = s[:32]
    if not seal.NICK_RE.match(s):
        return "thin-box"
    return s


def self_heal(cfg: ThinConfig, exe_dir: str, hostname: str) -> ThinConfig:
    if not cfg.home and exe_dir:
        cfg.home = exe_dir
    if not cfg.allow_path and cfg.home:
        cfg.allow_path = str(Path(cfg.home) / "jail")
    if not cfg.nick and hostname:
        cfg.nick = sanitize_hostname(hostname)
    if not cfg.hello and cfg.nick:
        cfg.hello = f"{cfg.nick}-online"
    return cfg


def merge_self_heal(ini: dict | None, argv: dict | None, exe_dir: str, hostname: str) -> ThinConfig:
    """INI then CLI (CLI wins), then fill empty home/jail/nick/hello. Does not wipe INI."""
    cfg = merge_config(ini, argv)
    return self_heal(cfg, exe_dir, hostname)


def validate_config(cfg: ThinConfig) -> None:
    if not cfg.nick or not seal.NICK_RE.match(cfg.nick):
        raise ValueError("invalid --nick")
    if not cfg.channel.startswith("#") or "|" in cfg.channel:
        raise ValueError("missing channel (add channel=#name to airc-moot-thin.ini beside the exe)")
    if not cfg.home:
        raise ValueError("missing --home")
    if not cfg.allow_path:
        raise ValueError("missing --allow-path")
    if cfg.chair or cfg.pairing:
        if cfg.pin and not pin_ok(cfg.pin):
            raise ValueError("invalid --pin (6 digits)")
        return
    if not MSGID_RE.match(cfg.moot_id or ""):
        raise ValueError("invalid --moot (16 hex)")
    require_operators(cfg.operators)


def wrap_key(pin: str, pair_id: str, channel: str, moot_id: str) -> bytes:
    if not pin_ok(pin) or not MSGID_RE.match(pair_id) or not MSGID_RE.match(moot_id):
        raise ValueError("invalid pin wrap inputs")
    s = f"{PIN_WRAP_LABEL}|{pin}|{pair_id.lower()}|{channel.lower()}|{moot_id.lower()}"
    return hashlib.sha256(s.encode("ascii")).digest()


def pair_offer_line(moot_id: str, pair_id: str, expires: int) -> str:
    return f"PAIR v1 OFFER {moot_id} {pair_id} {expires}"


def pair_ack_line(moot_id: str, pair_id: str) -> str:
    return f"PAIR v1 ACK {moot_id} {pair_id}"


def _gcm_seal(key: bytes, aad: bytes, plaintext: bytes) -> bytes:
    nonce = secrets.token_bytes(12)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, aad)


def _gcm_open(key: bytes, aad: bytes, blob: bytes) -> bytes:
    if len(blob) < 28:
        raise ValueError("pair blob short")
    return AESGCM(key).decrypt(blob[:12], blob[12:], aad)


def pair_hello_aad(channel: str, moot_id: str, pair_id: str) -> bytes:
    return f"{channel.lower()}|{moot_id.lower()}|{pair_id.lower()}|pair-hello-v1".encode("ascii")


def pair_grant_aad(channel: str, moot_id: str, pair_id: str, thin_nick: str) -> bytes:
    return (
        f"{channel.lower()}|{moot_id.lower()}|{pair_id.lower()}|{thin_nick.lower()}|pair-grant-v1"
    ).encode("ascii")


def pair_hello_seal(wrap: bytes, channel: str, moot_id: str, pair_id: str, nick: str) -> bytes:
    pt = json.dumps({"v": 1, "op": "hello", "nick": nick}, separators=(",", ":")).encode("utf-8")
    return _gcm_seal(wrap, pair_hello_aad(channel, moot_id, pair_id), pt)


def pair_hello_open(wrap: bytes, channel: str, moot_id: str, pair_id: str, blob: bytes) -> str:
    pt = json.loads(_gcm_open(wrap, pair_hello_aad(channel, moot_id, pair_id), blob))
    if pt.get("op") != "hello" or not seal.NICK_RE.match(pt.get("nick") or ""):
        raise ValueError("pair hello")
    return str(pt["nick"])


def pair_grant_seal(
    wrap: bytes,
    channel: str,
    moot_id: str,
    pair_id: str,
    thin_nick: str,
    chair_nick: str,
    psk: bytes,
) -> bytes:
    pt = json.dumps(
        {"v": 1, "op": "grant", "psk": psk.hex(), "chair": chair_nick, "moot": moot_id},
        separators=(",", ":"),
    ).encode("utf-8")
    return _gcm_seal(wrap, pair_grant_aad(channel, moot_id, pair_id, thin_nick), pt)


def pair_grant_open(
    wrap: bytes,
    channel: str,
    moot_id: str,
    pair_id: str,
    thin_nick: str,
    blob: bytes,
) -> tuple[bytes, str, str]:
    pt = json.loads(_gcm_open(wrap, pair_grant_aad(channel, moot_id, pair_id, thin_nick), blob))
    if pt.get("op") != "grant":
        raise ValueError("pair grant")
    psk = bytes.fromhex(pt["psk"])
    if len(psk) != 32:
        raise ValueError("pair grant psk")
    return psk, str(pt["chair"]), str(pt.get("moot") or moot_id)


def operators_add(raw: str, nick: str) -> str:
    ops = operators_set(raw)
    if nick and nick.lower() not in {x.lower() for x in ops}:
        ops.add(nick)
    return ",".join(sorted(ops, key=str.lower))


def moot_join_line(moot_id: str) -> str:
    return f"MOOT v1 JOIN {moot_id}"


def moot_open_line(moot_id: str, chair: str) -> str:
    return f"MOOT v1 OPEN {moot_id} {chair} floor :airc-moot-thin"


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
