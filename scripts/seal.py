#!/usr/bin/env python3
"""X25519 sealed box for agentic IRC. Ciphertext is safe on a public channel; keys are not."""
from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import sys
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

INFO = b"agentic-irc-seal-v1"
CHUNK = 300  # b64 payload per IRC line; keep PRIVMSG under ~400


def home() -> Path:
    raw = os.environ.get("AGENTIC_IRC_HOME")
    return Path(raw).expanduser() if raw else Path.home() / ".agentic-irc"


def ident_path() -> Path:
    return home() / "identity.json"


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def b64d(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"), validate=True)


def genkey(path: Path | None = None) -> dict:
    path = path or ident_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise SystemExit(f"identity already exists: {path}")
    sk = X25519PrivateKey.generate()
    pk = sk.public_key()
    doc = {
        "v": 1,
        "sk": b64(sk.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )),
        "pk": b64(pk.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )),
    }
    path.write_text(json.dumps(doc) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return doc


def load_ident(path: Path | None = None) -> dict:
    path = path or ident_path()
    if not path.exists():
        raise SystemExit(f"no identity at {path}; run: python scripts/seal.py genkey")
    return json.loads(path.read_text(encoding="utf-8"))


def seal_bytes(plaintext: bytes, recip_pk_b64: str) -> bytes:
    eph = X25519PrivateKey.generate()
    recip = X25519PublicKey.from_public_bytes(b64d(recip_pk_b64))
    shared = eph.exchange(recip)
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=INFO).derive(shared)
    nonce = secrets.token_bytes(12)
    ct = AESGCM(key).encrypt(nonce, plaintext, INFO)
    eph_pk = eph.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return eph_pk + nonce + ct


def open_bytes(blob: bytes, ident: dict) -> bytes:
    if len(blob) < 32 + 12 + 16:
        raise ValueError("ciphertext too short")
    eph_pk = X25519PublicKey.from_public_bytes(blob[:32])
    nonce = blob[32:44]
    ct = blob[44:]
    sk = X25519PrivateKey.from_private_bytes(b64d(ident["sk"]))
    shared = sk.exchange(eph_pk)
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=INFO).derive(shared)
    return AESGCM(key).decrypt(nonce, ct, INFO)


def irc_lines(blob: bytes, to_nick: str, msg_id: str | None = None) -> list[str]:
    payload = b64(blob)
    parts = [payload[i:i + CHUNK] for i in range(0, len(payload), CHUNK)] or [""]
    n = len(parts)
    msg_id = msg_id or secrets.token_hex(4)
    return [f"SEAL v1 {to_nick} {msg_id} {i + 1} {n} {part}" for i, part in enumerate(parts)]


def parse_seal_line(line: str) -> tuple[str, str, int, int, str] | None:
    parts = line.strip().split(" ", 6)
    if len(parts) != 7 or parts[0] != "SEAL" or parts[1] != "v1":
        return None
    _, _, to_nick, msg_id, i_s, n_s, b64part = parts
    return to_nick, msg_id, int(i_s), int(n_s), b64part


def main() -> None:
    p = argparse.ArgumentParser(description="agentic-irc sealed box")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("genkey", help="create ~/.agentic-irc/identity.json")
    sub.add_parser("pubkey", help="print AGPK v1 line for IRC")

    sp = sub.add_parser("seal", help="encrypt stdin/file to IRC SEAL lines")
    sp.add_argument("--to", required=True, help="recipient X25519 public key (base64)")
    sp.add_argument("--nick", default="peer", help="IRC nick to put in SEAL lines")
    sp.add_argument("--in", dest="infile", default="-", help="plaintext file or -")

    op = sub.add_parser("open", help="decrypt concatenated base64 or raw blob")
    op.add_argument("--in", dest="infile", default="-", help="file of concatenated b64 chunks or -")
    op.add_argument("--out", dest="outfile", default="-", help="plaintext dest or -")
    op.add_argument("--b64", action="store_true", help="input is base64 (default: auto)")

    args = p.parse_args()
    if args.cmd == "genkey":
        doc = genkey()
        print(f"wrote {ident_path()}", file=sys.stderr)
        print(f"AGPK v1 {doc['pk']}")
        return
    if args.cmd == "pubkey":
        print(f"AGPK v1 {load_ident()['pk']}")
        return
    if args.cmd == "seal":
        data = sys.stdin.buffer.read() if args.infile == "-" else Path(args.infile).read_bytes()
        blob = seal_bytes(data, args.to)
        for line in irc_lines(blob, args.nick):
            print(line)
        return
    if args.cmd == "open":
        raw = sys.stdin.buffer.read() if args.infile == "-" else Path(args.infile).read_bytes()
        try:
            blob = b64d(raw.decode("ascii").replace("\n", "").replace(" ", ""))
        except Exception:
            blob = raw
        pt = open_bytes(blob, load_ident())
        if args.outfile == "-":
            sys.stdout.buffer.write(pt)
        else:
            Path(args.outfile).write_bytes(pt)
            try:
                os.chmod(args.outfile, 0o600)
            except OSError:
                pass


if __name__ == "__main__":
    main()
