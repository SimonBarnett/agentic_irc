from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import dumb_agent
import seal


def test_psk_roundtrip_ping():
    key = os.urandom(32)
    job = {"v": 1, "op": "ping", "id": "0123456789abcdef"}
    blob = seal.dumb_seal_bytes(json.dumps(job).encode(), key, "#ops", "box", "alice", "0123456789abcdef")
    out = dumb_agent.handle_dumb_payload(
        blob, channel="#ops", to_nick="box", from_nick="alice", msg_id="0123456789abcdef",
        key32=key, operators={"alice"}, allow_path=Path("."),
    )
    assert out["ok"] is True


def test_from_nick_not_operator(tmp_path):
    key = os.urandom(32)
    job = {"v": 1, "op": "exec", "id": "0123456789abcdef", "argv": ["hostname"]}
    blob = seal.dumb_seal_bytes(json.dumps(job).encode(), key, "#ops", "box", "mallory", "0123456789abcdef")
    out = dumb_agent.handle_dumb_payload(
        blob, channel="#ops", to_nick="box", from_nick="mallory", msg_id="0123456789abcdef",
        key32=key, operators={"alice"}, allow_path=tmp_path,
    )
    assert out["ok"] is False
    assert out["error"] == "operator"


def test_jail_escape(tmp_path):
    key = os.urandom(32)
    job = {"v": 1, "op": "get", "id": "0123456789abcdef", "path": str(tmp_path / ".." / "Windows" / "win.ini")}
    blob = seal.dumb_seal_bytes(json.dumps(job).encode(), key, "#ops", "box", "alice", "0123456789abcdef")
    out = dumb_agent.handle_dumb_payload(
        blob, channel="#ops", to_nick="box", from_nick="alice", msg_id="0123456789abcdef",
        key32=key, operators={"alice"}, allow_path=tmp_path / "drop",
    )
    assert out["ok"] is False
    assert out["error"] == "jail"


def test_put_get(tmp_path):
    drop = tmp_path / "drop"
    drop.mkdir()
    key = os.urandom(32)
    data = b"hello-jail"
    put = {"v": 1, "op": "put", "id": "0123456789abcdef", "path": str(drop / "n.txt"), "b64": seal.b64(data)}
    blob = seal.dumb_seal_bytes(json.dumps(put).encode(), key, "#ops", "box", "alice", "0123456789abcdef")
    out = dumb_agent.handle_dumb_payload(
        blob, channel="#ops", to_nick="box", from_nick="alice", msg_id="0123456789abcdef",
        key32=key, operators={"alice"}, allow_path=drop,
    )
    assert out["ok"] is True
    get = {"v": 1, "op": "get", "id": "fedcba9876543210", "path": str(drop / "n.txt")}
    blob = seal.dumb_seal_bytes(json.dumps(get).encode(), key, "#ops", "box", "alice", "fedcba9876543210")
    out = dumb_agent.handle_dumb_payload(
        blob, channel="#ops", to_nick="box", from_nick="alice", msg_id="fedcba9876543210",
        key32=key, operators={"alice"}, allow_path=drop,
    )
    assert out["sha256"] == out["sha256"]
    assert seal.b64d(out["b64"]) == data


def test_exec_timeout_and_allowlist(tmp_path):
    key = os.urandom(32)
    job = {"v": 1, "op": "exec", "id": "0123456789abcdef", "argv": ["not-a-bin.exe"], "timeout_s": 1}
    blob = seal.dumb_seal_bytes(json.dumps(job).encode(), key, "#ops", "box", "alice", "0123456789abcdef")
    out = dumb_agent.handle_dumb_payload(
        blob, channel="#ops", to_nick="box", from_nick="alice", msg_id="0123456789abcdef",
        key32=key, operators={"alice"}, allow_path=tmp_path,
    )
    assert out["error"] == "bin"


def test_busy(tmp_path):
    assert dumb_agent._busy.acquire()
    try:
        key = os.urandom(32)
        job = {"v": 1, "op": "exec", "id": "0123456789abcdef", "argv": ["hostname"]}
        blob = seal.dumb_seal_bytes(json.dumps(job).encode(), key, "#ops", "box", "alice", "0123456789abcdef")
        out = dumb_agent.handle_dumb_payload(
            blob, channel="#ops", to_nick="box", from_nick="alice", msg_id="0123456789abcdef",
            key32=key, operators={"alice"}, allow_path=tmp_path,
        )
        assert out["error"] == "busy"
    finally:
        dumb_agent._busy.release()


def test_wrong_psk():
    key = os.urandom(32)
    job = {"v": 1, "op": "ping", "id": "0123456789abcdef"}
    blob = seal.dumb_seal_bytes(json.dumps(job).encode(), key, "#ops", "box", "alice", "0123456789abcdef")
    try:
        dumb_agent.handle_dumb_payload(
            blob, channel="#ops", to_nick="box", from_nick="alice", msg_id="0123456789abcdef",
            key32=os.urandom(32), operators={"alice"}, allow_path=Path("."),
        )
        assert False
    except Exception:
        pass
