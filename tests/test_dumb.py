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
import protect
import seal
import wire

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


def _dumb_args(home: Path, nick: str = "box", operators: str = "alice") -> argparse.Namespace:
    return argparse.Namespace(
        nick=nick,
        channel="#ops",
        home=str(home),
        operators=operators,
        allow_path=str(home / "drop"),
        hello="",
        host="127.0.0.1",
        port=6697,
        realname="test",
        once=True,
        allow_meta=False,
        allow_bin="",
    )


def _write_key(home: Path) -> bytes:
    key = os.urandom(32)
    protect.write_secret_bytes(home / "dumb" / "connector.key", key)
    return key


class _FakeSock:
    def __init__(self, inbound: bytes) -> None:
        self.inbound = inbound
        self.out = bytearray()

    def sendall(self, data: bytes) -> None:
        self.out.extend(data)

    def recv(self, n: int) -> bytes:
        if not self.inbound:
            return b""
        chunk, self.inbound = self.inbound[:n], self.inbound[n:]
        return chunk

    def close(self) -> None:
        pass


def test_exec_truncated_spills_results(tmp_path):
    big = "B" * 9000
    err = "e" * 20

    def runner(argv, cwd, timeout):
        return 0, big, err

    job = {"v": 1, "op": "exec", "id": JID, "argv": ["hostname"], "_runner": runner}
    out = dumb_agent.run_job(
        job,
        operators={"alice"},
        from_nick="alice",
        allow_path=tmp_path,
        allow_bin=set(dumb_agent.DEFAULT_BINS),
        home=tmp_path,
    )
    assert out["truncated"] is True
    assert len(out["stdout"]) + len(out["stderr"]) <= 8192
    spill = tmp_path / "dumb" / "results" / f"{JID}.txt"
    text = spill.read_text(encoding="utf-8")
    assert big in text
    assert err in text


def test_exec_not_truncated_no_spill(tmp_path):
    def runner(argv, cwd, timeout):
        return 0, "hi", ""

    job = {"v": 1, "op": "exec", "id": JID, "argv": ["hostname"], "_runner": runner}
    out = dumb_agent.run_job(
        job,
        operators={"alice"},
        from_nick="alice",
        allow_path=tmp_path,
        allow_bin=set(dumb_agent.DEFAULT_BINS),
        home=tmp_path,
    )
    assert out.get("truncated") is False
    assert not (tmp_path / "dumb" / "results" / f"{JID}.txt").exists()


def test_d2_unknown_operator_no_result_on_wire(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    monkeypatch.setattr(dumb_agent, "FLOOD_S", 0)
    (tmp_path / "drop").mkdir()
    key = _write_key(tmp_path)
    c = dumb_agent.Client(_dumb_args(tmp_path))
    ran: list[int] = []

    def boom(*a, **k):
        ran.append(1)
        return subprocess.CompletedProcess(a[0] if a else "hostname", 0, "", "")

    monkeypatch.setattr(subprocess, "run", boom)
    job = {"v": 1, "op": "exec", "id": JID, "argv": ["hostname"]}
    blob = seal.dumb_seal_bytes(json.dumps(job).encode(), key, "#ops", "box", "mallory", JID)
    for ln in seal.dumb_irc_lines(blob, "box", "mallory", JID):
        c.handle_privmsg("mallory!u@h", "#ops", ln)
    assert ran == []
    assert not any("DUMB v1" in x for x in c.sent)
    assert not any(x.startswith("PRIVMSG") for x in c.sent)


def test_operator_ping_emits_result_on_wire(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    monkeypatch.setattr(dumb_agent, "FLOOD_S", 0)
    (tmp_path / "drop").mkdir()
    key = _write_key(tmp_path)
    c = dumb_agent.Client(_dumb_args(tmp_path))
    job = {"v": 1, "op": "ping", "id": JID}
    blob = seal.dumb_seal_bytes(json.dumps(job).encode(), key, "#ops", "box", "alice", JID)
    for ln in seal.dumb_irc_lines(blob, "box", "alice", JID):
        c.handle_privmsg("alice!u@h", "#ops", ln)
    wire_lines = [x.split(" :", 1)[1] for x in c.sent if x.startswith("PRIVMSG") and "DUMB v1" in x]
    assert wire_lines
    store = seal.FragmentStore()
    got = None
    for ln in wire_lines:
        parsed = wire.parse_dumb_line(ln)
        assert parsed is not None
        got = store.add(parsed) or got
    assert got is not None
    pt = json.loads(seal.dumb_open_bytes(seal.b64d(got), key, "#ops", "alice", "box", JID).decode())
    assert pt["ok"] is True
    assert pt["op"] == "ping"


def test_listen_join_capa_offline(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_HOME", str(tmp_path))
    monkeypatch.setattr(dumb_agent, "FLOOD_S", 0)
    monkeypatch.setattr(dumb_agent, "SETTLE_S", 0)
    (tmp_path / "drop").mkdir()
    _write_key(tmp_path)
    fake = _FakeSock(b":srv 001 box :welcome\r\n:box!u@h JOIN :#ops\r\n")
    monkeypatch.setattr(dumb_agent.Client, "connect", lambda self: fake)
    c = dumb_agent.Client(_dumb_args(tmp_path))
    c.session()
    text = fake.out.decode("utf-8", "replace")
    assert "NICK box" in text
    assert "JOIN #ops" in text
    assert "CAPA v1 dumb" in text
    assert "no-listen" not in text
    src = Path(dumb_agent.__file__).read_text(encoding="utf-8")
    assert "no-listen" not in src


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
