#!/usr/bin/env python3
"""BEACON v1: publish airc-invite.json / .ini (no PSK). Offline helpers + optional gist."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import moot_thin_proto as thin

KIND = "airc-invite"
DEFAULT_HOST = "irc.libera.chat"
DEFAULT_PORT = 6697
DEFAULT_TTL_S = 600
FORBIDDEN = ("psk", "connector.key", "sasl", "identity.json", "password=")


@dataclass
class Invite:
    v: int
    kind: str
    host: str
    port: int
    channel: str
    moot: str
    pair: str
    pin: str
    expires: int
    chair: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "v": int(self.v),
            "kind": self.kind,
            "host": self.host,
            "port": int(self.port),
            "channel": self.channel,
            "moot": self.moot,
            "pair": self.pair,
            "pin": self.pin,
            "expires": int(self.expires),
            "chair": self.chair,
        }


def _reject_forbidden(text: str) -> None:
    low = text.lower()
    for bad in FORBIDDEN:
        if bad.lower() in low:
            raise ValueError(f"invite must not contain {bad}")


def make_invite(
    channel: str,
    moot: str,
    pin: str,
    pair: str,
    chair: str = "",
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    ttl_s: int = DEFAULT_TTL_S,
    now: int | None = None,
    expires: int | None = None,
) -> Invite:
    if now is None:
        now = int(time.time())
    if expires is None:
        expires = int(now) + int(ttl_s)
    inv = Invite(
        v=1,
        kind=KIND,
        host=host or DEFAULT_HOST,
        port=int(port),
        channel=channel,
        moot=moot,
        pair=pair,
        pin=pin,
        expires=int(expires),
        chair=chair or "",
    )
    _validate_invite(inv)
    return inv


def _validate_invite(inv: Invite) -> None:
    if int(inv.v) != 1:
        raise ValueError("airc-invite v")
    if inv.kind != KIND:
        raise ValueError("airc-invite")
    if not inv.channel.startswith("#") or "|" in inv.channel:
        raise ValueError("channel")
    if not thin.MSGID_RE.match(inv.moot or ""):
        raise ValueError("moot")
    if not thin.MSGID_RE.match(inv.pair or ""):
        raise ValueError("pair")
    if not thin.pin_ok(inv.pin):
        raise ValueError("pin")
    if inv.port <= 0 or inv.port > 65535:
        raise ValueError("port")


def dumps_json(inv: Invite) -> str:
    text = json.dumps(inv.as_dict(), separators=(",", ":"))
    _reject_forbidden(text)
    return text


def dumps_ini(inv: Invite) -> str:
    lines = [
        f"v={inv.v}",
        f"kind={inv.kind}",
        f"host={inv.host}",
        f"port={inv.port}",
        f"channel={inv.channel}",
        f"moot={inv.moot}",
        f"pair={inv.pair}",
        f"pin={inv.pin}",
        f"expires={inv.expires}",
        f"chair={inv.chair}",
        "",
    ]
    text = "\n".join(lines)
    _reject_forbidden(text)
    return text


def parse_invite(text: str) -> Invite:
    _reject_forbidden(text)
    raw = text.strip()
    if not raw:
        raise ValueError("airc-invite")
    if raw.startswith("{"):
        doc = json.loads(raw)
        if not isinstance(doc, dict):
            raise ValueError("airc-invite")
        kind = str(doc.get("kind") or "")
        if kind != KIND:
            raise ValueError("airc-invite")
        inv = Invite(
            v=int(doc.get("v") or 0),
            kind=kind,
            host=str(doc.get("host") or DEFAULT_HOST),
            port=int(doc.get("port") or DEFAULT_PORT),
            channel=str(doc.get("channel") or ""),
            moot=str(doc.get("moot") or ""),
            pair=str(doc.get("pair") or ""),
            pin=str(doc.get("pin") or ""),
            expires=int(doc.get("expires") or 0),
            chair=str(doc.get("chair") or ""),
        )
        _validate_invite(inv)
        return inv
    kv = thin.parse_ini(raw)
    kind = kv.get("kind") or ""
    if kind != KIND:
        raise ValueError("airc-invite")
    inv = Invite(
        v=int(kv.get("v") or 0),
        kind=kind,
        host=kv.get("host") or DEFAULT_HOST,
        port=int(kv.get("port") or DEFAULT_PORT),
        channel=kv.get("channel") or "",
        moot=kv.get("moot") or kv.get("mootid") or "",
        pair=kv.get("pair") or "",
        pin=kv.get("pin") or "",
        expires=int(kv.get("expires") or 0),
        chair=kv.get("chair") or "",
    )
    _validate_invite(inv)
    return inv


def expired(inv: Invite, now: int | None = None) -> bool:
    if now is None:
        now = int(time.time())
    return int(now) >= int(inv.expires)


def apply_invite(cfg: thin.ThinConfig, inv: Invite, now: int | None = None) -> thin.ThinConfig:
    if expired(inv, now=now):
        raise ValueError("expired")
    cfg.host = inv.host
    cfg.port = int(inv.port)
    cfg.channel = inv.channel
    cfg.moot_id = inv.moot
    cfg.pin = inv.pin
    cfg.pairing = True
    if hasattr(cfg, "from_nick") and inv.chair:
        if not cfg.from_nick:
            cfg.from_nick = inv.chair
    return cfg


def write_pack(inv: Invite, out_dir: str | Path) -> list[Path]:
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    jp = d / "airc-invite.json"
    ip = d / "airc-invite.ini"
    jp.write_text(dumps_json(inv) + "\n", encoding="utf-8")
    ip.write_text(dumps_ini(inv), encoding="utf-8")
    return [jp, ip]


def fetch_text(url: str, timeout: float = 15.0) -> str:
    if not url.lower().startswith("https://"):
        raise ValueError("https")
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.URLError as e:
        raise ValueError(str(e)) from e


def load_beacon_url_file(path: str | Path) -> str:
    text = Path(path).read_text(encoding="utf-8")
    for line in text.splitlines():
        u = line.strip()
        if not u or u.startswith("#"):
            continue
        if not u.lower().startswith("https://"):
            raise ValueError("https")
        return u
    raise ValueError("https")


def resolve_invite(
    path: str | Path | None = None,
    url: str | None = None,
    beacon_url_file: str | Path | None = None,
    now: int | None = None,
) -> Invite:
    text = None
    if path:
        text = Path(path).read_text(encoding="utf-8")
    elif beacon_url_file:
        text = fetch_text(load_beacon_url_file(beacon_url_file))
    elif url:
        text = fetch_text(url)
    else:
        raise ValueError("airc-invite")
    inv = parse_invite(text)
    if expired(inv, now=now):
        raise ValueError("expired")
    return inv


def _gist(inv: Invite, out_dir: Path) -> Path:
    tmp = out_dir / "airc-invite.json"
    cmd = ["gh", "gist", "create", "--secret", str(tmp)]
    raw = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if raw.returncode != 0:
        raise SystemExit(raw.stderr or "gh gist create failed")
    gist = (raw.stdout or "").strip().splitlines()[-1].strip()
    if "gist.github.com" in gist and "/raw/" not in gist:
        gist = gist.rstrip("/") + "/raw/airc-invite.json"
    if not gist.lower().startswith("https://"):
        raise SystemExit("gist url was not https")
    bp = out_dir / "beacon.url"
    bp.write_text(gist + "\n", encoding="utf-8")
    return bp


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="beacon.py")
    sub = p.add_subparsers(dest="cmd", required=True)
    mk = sub.add_parser("make")
    mk.add_argument("--channel", required=True)
    mk.add_argument("--moot", required=True)
    mk.add_argument("--pin", required=True)
    mk.add_argument("--pair", required=True)
    mk.add_argument("--chair", default="")
    mk.add_argument("--host", default=DEFAULT_HOST)
    mk.add_argument("--port", type=int, default=DEFAULT_PORT)
    mk.add_argument("--ttl", type=int, default=DEFAULT_TTL_S)
    mk.add_argument("--out-dir", required=True)
    mk.add_argument("--gist", action="store_true")
    ck = sub.add_parser("check")
    ck.add_argument("--in", dest="infile")
    ck.add_argument("--beacon-url-file")
    args = p.parse_args(argv)
    if args.cmd == "make":
        inv = make_invite(
            channel=args.channel,
            moot=args.moot,
            pin=args.pin,
            pair=args.pair,
            chair=args.chair,
            host=args.host,
            port=args.port,
            ttl_s=args.ttl,
        )
        out = Path(args.out_dir)
        write_pack(inv, out)
        if args.gist:
            _gist(inv, out)
        return 0
    inv = resolve_invite(path=args.infile, beacon_url_file=args.beacon_url_file)
    sys.stdout.write(dumps_json(inv) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
