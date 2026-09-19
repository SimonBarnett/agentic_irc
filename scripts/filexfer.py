#!/usr/bin/env python3
"""FILE v1 offer/accept/chunk reassembly. Tier S uses SEAL v2 envelope; M is clear CHUNKs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import protect
import seal
import wire

MAX_N_FILE = 320
FILE_TTL_S = 1800
FILES_HOME_CAP = 64 * 1024 * 1024


def files_bytes_used(home: Path) -> int:
    root = Path(home) / "files"
    if not root.exists():
        return 0
    total = 0
    for p in root.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                continue
    return total


def would_exceed_cap(home: Path, extra: int = 0) -> bool:
    return files_bytes_used(home) + extra > FILES_HOME_CAP


class FileBag:
    def __init__(self) -> None:
        self._bags: dict[tuple[str, str], dict] = {}
        self._offers: dict[str, dict] = {}
        self._assembled: dict[str, bytes] = {}
        self._aborted: set[str] = set()

    def note_offer(self, src: str, fid: str, name: str, sha: str, nbytes: str | int, tier: str) -> bool:
        """First OFFER for an id wins. Second OFFER same id is ignored (PDF F6)."""
        key = fid.lower()
        if key in self._offers:
            return False
        try:
            size = int(nbytes)
        except (TypeError, ValueError):
            size = 0
        self._offers[key] = {
            "src": src,
            "name": name,
            "sha": sha,
            "bytes": size,
            "tier": tier,
        }
        return True

    def abort(self, fid: str) -> None:
        """FILE v1 ABORT: drop in-flight bag and assembled bytes. No complete/ write."""
        fid_l = fid.lower()
        self._aborted.add(fid_l)
        for k in [k for k in self._bags if k[1] == fid_l]:
            del self._bags[k]
        self._assembled.pop(fid_l, None)

    def take_assembled(self, fid: str) -> bytes | None:
        return self._assembled.pop(fid.lower(), None)

    def add_chunk(self, from_nick: str, fid: str, i: int, n: int, b64: str, now: float | None = None) -> bytes | None:
        now = time.time() if now is None else now
        dead = [k for k, b in self._bags.items() if now - b["t0"] > FILE_TTL_S]
        for k in dead:
            del self._bags[k]
        if n > MAX_N_FILE or i < 1 or i > n:
            return None
        if fid.lower() in self._aborted:
            return None
        key = (from_nick.lower(), fid.lower())
        bag = self._bags.get(key)
        if bag is None:
            bag = {"n": n, "parts": {}, "t0": now}
            self._bags[key] = bag
        if bag["n"] != n:
            return None
        bag["parts"][i] = b64
        if len(bag["parts"]) < n:
            return None
        raw = "".join(bag["parts"][j] for j in range(1, n + 1))
        del self._bags[key]
        try:
            data = seal.b64d(raw)
        except Exception:
            return None
        self._assembled[fid.lower()] = data
        return data


def _home(h: str | None) -> Path:
    if h:
        os.environ["AGENTIC_IRC_HOME"] = str(Path(h).expanduser())
    return seal.home()


def offer(args: argparse.Namespace) -> None:
    home = _home(args.home)
    path = Path(args.infile)
    if path.name in {"identity.json", "connector.key"} or "inbox" in path.parts:
        raise SystemExit("refuse secret path")
    data = path.read_bytes()
    h = hashlib.sha256(data).hexdigest()
    fid = secrets.token_hex(8)
    tier = args.tier
    name = path.name
    if not wire.FILE_NAME_RE.match(name):
        raise SystemExit("bad name")
    line = f"FILE v1 OFFER {args.to} {args.from_nick} {fid} {len(data)} {h} {tier} {name}"
    (home / "outbox.txt").open("a", encoding="utf-8").write(line + "\n")
    meta = home / "files" / "outgoing" / fid
    meta.mkdir(parents=True, exist_ok=True)
    (meta / "manifest.json").write_text(json.dumps({"id": fid, "name": name, "sha256": h, "bytes": len(data)}) + "\n")
    (meta / "data.bin").write_bytes(data)
    if tier == "S":
        ident = seal.load_ident()
        peers = seal.load_peers()
        pk = peers.get(args.to.lower(), {}).get("pk")
        if not pk:
            raise SystemExit("no AGPK pin for recipient")
        blob = seal.seal_bytes_v2(data, pk, ident, args.channel, args.to, args.from_nick, fid)
        for ln in seal.irc_lines_v2(blob, args.to, args.from_nick, fid):
            (home / "outbox.txt").open("a", encoding="utf-8").write(ln + "\n")
    elif tier == "M":
        b64 = seal.b64(data)
        parts = [b64[i : i + seal.CHUNK] for i in range(0, len(b64), seal.CHUNK)] or [""]
        n = len(parts)
        if n > MAX_N_FILE:
            raise SystemExit("too many chunks")
        for i, part in enumerate(parts, 1):
            (home / "outbox.txt").open("a", encoding="utf-8").write(f"FILE v1 CHUNK {fid} {i} {n} {part}\n")
        (home / "outbox.txt").open("a", encoding="utf-8").write(f"FILE v1 DONE {fid} {h}\n")
    print(fid)


def complete_write(home: Path, fid: str, name: str, data: bytes, sha: str) -> bool:
    if hashlib.sha256(data).hexdigest() != sha:
        return False
    dest = home / "files" / "complete" / f"{fid}-{name}"
    if dest.exists():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    protect.protect_path(dest)
    return True


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--home", default="")
    sub = p.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("offer")
    o.add_argument("--channel", default="#ops")
    o.add_argument("--from-nick", required=True)
    o.add_argument("--to", required=True)
    o.add_argument("--in", dest="infile", required=True)
    o.add_argument("--tier", default="M", choices=["S", "M", "L"])
    a = sub.add_parser("accept")
    a.add_argument("--id", required=True)
    r = sub.add_parser("refuse")
    r.add_argument("--id", required=True)
    r.add_argument("--reason", default="")
    s = sub.add_parser("status")
    s.add_argument("--id", required=True)
    args = p.parse_args()
    if args.cmd == "offer":
        offer(args)
    elif args.cmd == "accept":
        home = _home(args.home)
        if would_exceed_cap(home):
            (home / "outbox.txt").open("a", encoding="utf-8").write(f"FILE v1 REFUSE {args.id} :disk\n")
        else:
            (home / "outbox.txt").open("a", encoding="utf-8").write(f"FILE v1 ACCEPT {args.id}\n")
    elif args.cmd == "refuse":
        home = _home(args.home)
        (home / "outbox.txt").open("a", encoding="utf-8").write(f"FILE v1 REFUSE {args.id} :{args.reason}\n")
    elif args.cmd == "status":
        print(args.id)


if __name__ == "__main__":
    main()
