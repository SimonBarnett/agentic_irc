from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import dumb_agent
import irc_agent
import seal

JID = "0123456789abcdef"


def _args(home: Path, nick: str = "box") -> argparse.Namespace:
    return argparse.Namespace(
        nick=nick,
        channel="#ops",
        home=str(home),
        outbox="",
        hello="",
        announce_key=False,
        host="127.0.0.1",
        port=6697,
        realname="test",
        once=True,
    )


def _blob(job, key, from_nick="alice", to_nick="box", msg_id=JID):
    return seal.dumb_seal_bytes(json.dumps(job).encode(), key, "#ops", to_nick, from_nick, msg_id)


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
    drop = tmp_path / "agent-drop"
    drop.mkdir()
    job = {"v": 1, "op": "get", "id": JID, "path": str(drop / ".." / "Windows" / "win.ini")}
    blob = _blob(job, key)
    out = dumb_agent.handle_dumb_payload(
        blob, channel="#ops", to_nick="box", from_nick="alice", msg_id=JID,
        key32=key, operators={"alice"}, allow_path=drop,
    )
    assert out["ok"] is False
    assert out["error"] == "jail"


def test_jail_unc_and_secret_name(tmp_path):
    key = os.urandom(32)
    drop = tmp_path / "drop"
    drop.mkdir()
    (drop / "identity.json").write_text("{}")
    for path in (r"\\server\share\x", "//server/share/x", str(drop / "identity.json")):
        job = {"v": 1, "op": "get", "id": JID, "path": path}
        out = dumb_agent.handle_dumb_payload(
            _blob(job, key), channel="#ops", to_nick="box", from_nick="alice", msg_id=JID,
            key32=key, operators={"alice"}, allow_path=drop,
        )
        assert out["ok"] is False
        assert out["error"] == "jail", path
    put = {"v": 1, "op": "put", "id": JID, "path": str(drop / "connector.key"), "b64": seal.b64(b"nope")}
    out = dumb_agent.handle_dumb_payload(
        _blob(put, key), channel="#ops", to_nick="box", from_nick="alice", msg_id=JID,
        key32=key, operators={"alice"}, allow_path=drop,
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
    assert out["sha256"] == hashlib.sha256(data).hexdigest()
    assert seal.b64d(out["b64"]) == data


def test_exec_allowlist_miss(tmp_path):
    key = os.urandom(32)
    job = {"v": 1, "op": "exec", "id": JID, "argv": ["not-a-bin.exe"], "timeout_s": 1}
    out = dumb_agent.handle_dumb_payload(
        _blob(job, key), channel="#ops", to_nick="box", from_nick="alice", msg_id=JID,
        key32=key, operators={"alice"}, allow_path=tmp_path,
    )
    assert out["ok"] is False
    assert out["error"] == "bin"


def test_exec_timeout_monkeypatch(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd=a[0] if a else "hostname", timeout=k.get("timeout", 1))

    monkeypatch.setattr(subprocess, "run", boom)
    key = os.urandom(32)
    job = {"v": 1, "op": "exec", "id": JID, "argv": ["hostname"], "timeout_s": 1}
    out = dumb_agent.handle_dumb_payload(
        _blob(job, key), channel="#ops", to_nick="box", from_nick="alice", msg_id=JID,
        key32=key, operators={"alice"}, allow_path=tmp_path,
    )
    assert out["ok"] is False
    assert out["error"] == "timeout"


def test_d8_meta_chars_rejected(tmp_path):
    key = os.urandom(32)
    job = {"v": 1, "op": "exec", "id": JID, "argv": ["cmd.exe", "/c", "dir & whoami"]}
    out = dumb_agent.handle_dumb_payload(
        _blob(job, key), channel="#ops", to_nick="box", from_nick="alice", msg_id=JID,
        key32=key, operators={"alice"}, allow_path=tmp_path,
    )
    assert out["ok"] is False
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
    job = {"v": 1, "op": "ping", "id": JID}
    blob = _blob(job, key)
    with pytest.raises(Exception):
        dumb_agent.handle_dumb_payload(
            blob, channel="#ops", to_nick="box", from_nick="alice", msg_id=JID,
            key32=os.urandom(32), operators={"alice"}, allow_path=Path("."),
        )


def test_d9_prefix_not_from_nick(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    seal.genkey()
    c = irc_agent.Client(_args(tmp_path, "box"))
    key = os.urandom(32)
    job = {"v": 1, "op": "ping", "id": JID}
    blob = _blob(job, key)
    line = seal.dumb_irc_lines(blob, "box", "alice", JID)[0]
    c.handle_privmsg("mallory!u@h", "#ops", line)
    err = capsys.readouterr().out
    assert "prefix != from_nick" in err
    assert "INFO dumb job" not in err
    c.handle_privmsg("alice!u@h", "#ops", line)
    err2 = capsys.readouterr().out
    assert "INFO dumb job" in err2


def test_empty_operators_refused(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        ["dumb_agent.py", "--nick", "box", "--channel", "#ops", "--home", ".", "--operators", "", "--allow-path", "."],
    )
    with pytest.raises(SystemExit, match="operators"):
        dumb_agent.main()


@pytest.mark.skipif(not os.environ.get("DOTNET_DUMB_EXE"), reason="DOTNET_DUMB_EXE not set")
def test_dotnet_exe_if_present():
    exe = os.environ["DOTNET_DUMB_EXE"]
    r = subprocess.run([exe], capture_output=True, text=True, timeout=10)
    assert r.returncode == 0
    assert "INFO" in (r.stdout or "")
