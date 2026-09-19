#!/usr/bin/env python3
"""Python dumb connector: jail + allowlisted exec/get/put. No LLM. Offline-testable."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import protect
import seal
import wire

DEFAULT_BINS = frozenset({"cmd.exe", "powershell.exe", "hostname.exe", "ipconfig.exe", "whoami.exe", "hostname", "ipconfig", "whoami"})
META_CHARS = frozenset("&|><^")
_busy = threading.Lock()


def jail_root(allow: str) -> Path:
    p = Path(allow).resolve()
    p.mkdir(parents=True, exist_ok=True)
    protect.protect_path(p)
    return p


def in_jail(root: Path, target: Path) -> bool:
    try:
        raw = str(target)
        if raw.startswith("\\\\") or raw.startswith("//"):
            return False
        t = target.resolve()
        r = root.resolve()
        ts, rs = str(t), str(r)
        if ts.startswith("\\\\") or ts.startswith("//"):
            return False
        return r == t or r in t.parents
    except Exception:
        return False


def run_job(job: dict, *, operators: set[str], from_nick: str, allow_path: Path, allow_bin: set[str], allow_meta: bool = False) -> dict:
    if from_nick.lower() not in {x.lower() for x in operators}:
        return {"v": 1, "op": job.get("op"), "id": job.get("id"), "ok": False, "error": "operator"}
    op = job.get("op")
    jid = job.get("id", "")
    if op == "ping":
        return {"v": 1, "op": "ping", "id": jid, "ok": True, "rc": 0}
    if op == "sysinfo":
        return {
            "v": 1,
            "op": "sysinfo",
            "id": jid,
            "ok": True,
            "sys": {"os": sys.platform, "machine": os.environ.get("COMPUTERNAME", ""), "user": os.environ.get("USERNAME", "")},
        }
    if op in {"get", "put"}:
        raw = job.get("path") or job.get("cwd") or ""
        if str(raw).startswith("\\\\") or str(raw).startswith("//"):
            return {"v": 1, "op": op, "id": jid, "ok": False, "error": "jail"}
        dest = Path(raw)
        if not dest.is_absolute():
            dest = allow_path / dest
        if not in_jail(allow_path, dest):
            return {"v": 1, "op": op, "id": jid, "ok": False, "error": "jail"}
        if dest.name in {"identity.json", "connector.key", "peers.json"}:
            return {"v": 1, "op": op, "id": jid, "ok": False, "error": "jail"}
        if op == "get":
            data = dest.read_bytes()
            return {"v": 1, "op": "get", "id": jid, "ok": True, "sha256": hashlib.sha256(data).hexdigest(), "b64": seal.b64(data) if len(data) <= 12 * 1024 else ""}
        raw_b = seal.b64d(job.get("b64", "")) if job.get("b64") else b""
        dest.write_bytes(raw_b)
        return {"v": 1, "op": "put", "id": jid, "ok": True, "sha256": hashlib.sha256(raw_b).hexdigest()}
    if op == "exec":
        if not _busy.acquire(blocking=False):
            return {"v": 1, "op": "exec", "id": jid, "ok": False, "error": "busy"}
        try:
            argv = job.get("argv") or []
            if not argv:
                return {"v": 1, "op": "exec", "id": jid, "ok": False, "error": "bin"}
            bin0 = Path(str(argv[0])).name.lower()
            if bin0 not in {x.lower() for x in allow_bin}:
                return {"v": 1, "op": "exec", "id": jid, "ok": False, "error": "bin"}
            joined = " ".join(str(x) for x in argv)
            if any(tok in joined for tok in ("..", "\\\\", "//")):
                return {"v": 1, "op": "exec", "id": jid, "ok": False, "error": "jail"}
            if not allow_meta and any(ch in joined for ch in META_CHARS):
                return {"v": 1, "op": "exec", "id": jid, "ok": False, "error": "bin"}
            timeout = int(job.get("timeout_s") or 20)
            timeout = max(1, min(60, timeout))
            cwd = job.get("cwd") or str(allow_path)
            if str(cwd).startswith("\\\\") or str(cwd).startswith("//"):
                return {"v": 1, "op": "exec", "id": jid, "ok": False, "error": "jail"}
            if not in_jail(allow_path, Path(cwd)):
                return {"v": 1, "op": "exec", "id": jid, "ok": False, "error": "jail"}
            runner = job.get("_runner") if callable(job.get("_runner")) else None
            if runner:
                rc, out, err = runner(argv, cwd, timeout)
            else:
                p = subprocess.run(argv, cwd=cwd, capture_output=True, timeout=timeout, text=True)
                rc, out, err = p.returncode, p.stdout or "", p.stderr or ""
            trunc = False
            if len(out) + len(err) > 8192:
                trunc = True
                out, err = out[:4000], err[:4000]
            return {"v": 1, "op": "exec", "id": jid, "ok": rc == 0, "rc": rc, "stdout": out, "stderr": err, "truncated": trunc}
        except subprocess.TimeoutExpired:
            return {"v": 1, "op": "exec", "id": jid, "ok": False, "error": "timeout"}
        finally:
            _busy.release()
    return {"v": 1, "op": op, "id": jid, "ok": False, "error": "op"}


def handle_dumb_payload(
    body: bytes,
    *,
    channel: str,
    to_nick: str,
    from_nick: str,
    msg_id: str,
    key32: bytes,
    operators: set[str],
    allow_path: Path,
    allow_bin: set[str] | None = None,
    allow_meta: bool = False,
) -> dict:
    pt = seal.dumb_open_bytes(body, key32, channel, to_nick, from_nick, msg_id)
    job = json.loads(pt.decode("utf-8"))
    return run_job(
        job,
        operators=operators,
        from_nick=from_nick,
        allow_path=allow_path,
        allow_bin=allow_bin or DEFAULT_BINS,
        allow_meta=allow_meta,
    )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--nick", required=True)
    p.add_argument("--channel", required=True)
    p.add_argument("--home", required=True)
    p.add_argument("--operators", required=True)
    p.add_argument("--allow-path", required=True)
    p.add_argument("--hello", default="")
    args = p.parse_args()
    if not args.operators.strip():
        raise SystemExit("installer MUST refuse empty --operators")
    os.environ["AGENTIC_IRC_HOME"] = args.home
    print(f"INFO dumb connector {args.nick} jail={args.allow_path}")
    print("INFO no-listen; use tests or irc_agent for the socket loop")


if __name__ == "__main__":
    main()
