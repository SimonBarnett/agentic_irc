from __future__ import annotations

import hashlib
import json
import os
import socket
import ssl
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import protect
import seal
import wire

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "dumb_dotnet"
JID = "0123456789abcdef"


def _exe() -> str | None:
    env = os.environ.get("DOTNET_DUMB_EXE")
    if env and Path(env).exists():
        return env
    cand = SRC / "airc-dumb.exe"
    if cand.exists():
        return str(cand)
    return None


def test_csproj_net45_no_nuget_crypto():
    csproj = (SRC / "airc-dumb.csproj").read_text(encoding="utf-8")
    assert "<TargetFrameworkVersion>v4.5</TargetFrameworkVersion>" in csproj
    assert "packages.config" not in csproj
    assert "PackageReference" not in csproj
    blob = "\n".join(p.read_text(encoding="utf-8") for p in SRC.glob("*.cs"))
    assert "SslStream" in blob
    assert "Tls12" in blob
    assert "CAPA v1 dumb" in blob
    assert "dumb-v1" in blob
    assert "truncated" in blob
    readme = (SRC / "README.md").read_text(encoding="utf-8")
    assert "stub" not in readme.lower() or "protocol clone" in readme.lower()
    skill = (ROOT / ".grok" / "skills" / "agentic-dumb" / "SKILL.md").read_text(encoding="utf-8")
    assert "stub" not in skill.lower()
    assert "not ready for human uat" in skill.lower() or "not claimed ready for human uat" in skill.lower()


@pytest.mark.skipif(_exe() is None, reason="airc-dumb.exe not built")
def test_dotnet_selftest():
    r = subprocess.run([_exe(), "--selftest"], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    out = r.stdout or ""
    assert "selftest ok" in out
    assert "D2 no result ciphertext ok" in out
    assert "aesgcm vector ok" in out


@pytest.mark.skipif(_exe() is None, reason="airc-dumb.exe not built")
def test_dotnet_empty_operators(tmp_path):
    r = subprocess.run(
        [
            _exe(),
            "--offline",
            "--nick",
            "box",
            "--channel",
            "#ops",
            "--home",
            str(tmp_path),
            "--allow-path",
            str(tmp_path),
            "--operators",
            "",
            "--from-nick",
            "alice",
            "--job-in",
            str(tmp_path / "missing.json"),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode != 0
    text = (r.stdout or "") + (r.stderr or "")
    assert "operators" in text.lower()


def _offline(tmp_path: Path, job: dict, from_nick: str = "alice", operators: str = "alice") -> dict:
    jin = tmp_path / "job.json"
    jout = tmp_path / "out.json"
    jin.write_text(json.dumps(job), encoding="utf-8")
    r = subprocess.run(
        [
            _exe(),
            "--offline",
            "--nick",
            "box",
            "--channel",
            "#ops",
            "--home",
            str(tmp_path),
            "--allow-path",
            str(tmp_path / "drop"),
            "--operators",
            operators,
            "--from-nick",
            from_nick,
            "--job-in",
            str(jin),
            "--job-out",
            str(jout),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(jout.read_text(encoding="utf-8"))


@pytest.mark.skipif(_exe() is None, reason="airc-dumb.exe not built")
def test_dotnet_offline_ping(tmp_path):
    (tmp_path / "drop").mkdir()
    out = _offline(tmp_path, {"v": 1, "op": "ping", "id": JID})
    assert out["ok"] is True
    assert out["op"] == "ping"
    assert out["rc"] == 0


@pytest.mark.skipif(_exe() is None, reason="airc-dumb.exe not built")
def test_dotnet_offline_operator_drop(tmp_path):
    (tmp_path / "drop").mkdir()
    out = _offline(tmp_path, {"v": 1, "op": "exec", "id": JID, "argv": ["hostname"]}, from_nick="mallory")
    assert out["ok"] is False
    assert out["error"] == "operator"


@pytest.mark.skipif(_exe() is None, reason="airc-dumb.exe not built")
def test_dotnet_offline_jail(tmp_path):
    drop = tmp_path / "drop"
    drop.mkdir()
    out = _offline(tmp_path, {"v": 1, "op": "get", "id": JID, "path": str(drop / ".." / "Windows" / "win.ini")})
    assert out["ok"] is False
    assert out["error"] == "jail"
    out2 = _offline(tmp_path, {"v": 1, "op": "get", "id": JID, "path": r"\\server\share\x"})
    assert out2["error"] == "jail"


@pytest.mark.skipif(_exe() is None, reason="airc-dumb.exe not built")
def test_dotnet_offline_put_get(tmp_path):
    drop = tmp_path / "drop"
    drop.mkdir()
    data = b"hello-jail"
    put = {
        "v": 1,
        "op": "put",
        "id": JID,
        "path": str(drop / "n.txt"),
        "b64": seal.b64(data),
    }
    out = _offline(tmp_path, put)
    assert out["ok"] is True
    assert out["sha256"] == hashlib.sha256(data).hexdigest()
    got = _offline(tmp_path, {"v": 1, "op": "get", "id": "fedcba9876543210", "path": str(drop / "n.txt")})
    assert got["ok"] is True
    assert got["sha256"] == hashlib.sha256(data).hexdigest()
    assert seal.b64d(got["b64"]) == data


@pytest.mark.skipif(_exe() is None, reason="airc-dumb.exe not built")
def test_dotnet_offline_exec_hostname(tmp_path):
    (tmp_path / "drop").mkdir()
    out = _offline(tmp_path, {"v": 1, "op": "exec", "id": JID, "argv": ["hostname"], "timeout_s": 10})
    assert out["op"] == "exec"
    assert "rc" in out
    assert "stdout" in out
    assert out.get("truncated") is False


@pytest.mark.skipif(_exe() is None, reason="airc-dumb.exe not built")
def test_dotnet_offline_meta_rejected(tmp_path):
    (tmp_path / "drop").mkdir()
    out = _offline(tmp_path, {"v": 1, "op": "exec", "id": JID, "argv": ["cmd.exe", "/c", "dir & whoami"]})
    assert out["ok"] is False
    assert out["error"] == "meta"


@pytest.mark.skipif(_exe() is None, reason="airc-dumb.exe not built")
def test_dotnet_offline_truncation_spill(tmp_path):
    """Spill path is covered by --selftest; here exec of a small job must not spill."""
    (tmp_path / "drop").mkdir()
    out = _offline(tmp_path, {"v": 1, "op": "exec", "id": JID, "argv": ["hostname"]})
    assert out.get("truncated") is False
    assert not (tmp_path / "dumb" / "results" / f"{JID}.txt").exists()


def _make_tls_pair(tmp_path: Path) -> tuple[Path, Path]:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    cert_pem = tmp_path / "srv.crt"
    key_pem = tmp_path / "srv.key"
    cert_pem.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_pem.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    return cert_pem, key_pem


class _IrcTls:
    def __init__(self, cert: Path, key: Path) -> None:
        self.got: list[str] = []
        self._send: list[bytes] = []
        self._cv = threading.Condition()
        self.port = 0
        self.err: str | None = None
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._sock: socket.socket | None = None
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(str(cert), str(key))
        self._ctx = ctx
        self._th = threading.Thread(target=self._run, daemon=True)

    def start(self) -> int:
        self._th.start()
        if not self._ready.wait(10):
            raise TimeoutError("listen")
        if self.err:
            raise RuntimeError(self.err)
        return self.port

    def send_line(self, line: str) -> None:
        with self._cv:
            self._send.append((line + "\r\n").encode("utf-8"))
            self._cv.notify_all()

    def wait_privmsg_contains(self, needle: str, timeout: float = 20.0) -> str:
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._cv:
                for ln in self.got:
                    if needle in ln:
                        return ln
            time.sleep(0.05)
        raise TimeoutError("missing " + needle + " in " + repr(self.got))

    def stop(self) -> None:
        self._stop.set()
        try:
            if self._sock:
                self._sock.close()
        except OSError:
            pass

    def _run(self) -> None:
        ls = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        ls.bind(("127.0.0.1", 0))
        ls.listen(1)
        ls.settimeout(1.0)
        self._sock = ls
        self.port = ls.getsockname()[1]
        self._ready.set()
        ssock = None
        try:
            while not self._stop.is_set():
                try:
                    conn, _addr = ls.accept()
                except socket.timeout:
                    continue
                ssock = self._ctx.wrap_socket(conn, server_side=True)
                ssock.settimeout(0.3)
                buf = b""
                nick = "box"
                sent_001 = False
                while not self._stop.is_set():
                    with self._cv:
                        pending = list(self._send)
                        self._send.clear()
                    for chunk in pending:
                        ssock.sendall(chunk)
                    try:
                        data = ssock.recv(4096)
                    except ssl.SSLError:
                        data = b""
                    except socket.timeout:
                        data = b""
                    if data:
                        buf += data
                        while b"\n" in buf:
                            raw, buf = buf.split(b"\n", 1)
                            line = raw.decode("utf-8", "replace").rstrip("\r")
                            with self._cv:
                                self.got.append(line)
                            parts = line.split(" ")
                            cmd = parts[0] if parts else ""
                            if cmd == "NICK" and len(parts) > 1:
                                nick = parts[1]
                            if cmd in ("NICK", "USER", "CAP") and not sent_001:
                                ssock.sendall(f":srv 001 {nick} :welcome\r\n".encode("utf-8"))
                                sent_001 = True
                            if cmd == "JOIN":
                                ch = parts[1] if len(parts) > 1 else "#ops"
                                ssock.sendall(f":{nick}!u@h JOIN :{ch}\r\n".encode("utf-8"))
                    elif data == b"" and not sent_001:
                        pass
        except Exception as e:
            self.err = str(e)
        finally:
            try:
                if ssock:
                    ssock.close()
            except OSError:
                pass
            try:
                ls.close()
            except OSError:
                pass


@pytest.mark.skipif(_exe() is None, reason="airc-dumb.exe not built")
def test_dotnet_tls_capa_d2_ping(tmp_path):
    drop = tmp_path / "drop"
    drop.mkdir()
    key = os.urandom(32)
    protect.write_secret_bytes(tmp_path / "dumb" / "connector.key", key)
    cert, pkey = _make_tls_pair(tmp_path)
    srv = _IrcTls(cert, pkey)
    port = srv.start()
    proc = subprocess.Popen(
        [
            _exe(),
            "--nick",
            "box",
            "--channel",
            "#ops",
            "--home",
            str(tmp_path),
            "--allow-path",
            str(drop),
            "--operators",
            "alice",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--once",
            "--tls-insecure",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        capa = srv.wait_privmsg_contains("CAPA v1 dumb", timeout=25)
        parsed = wire.parse_capa_line(capa.split(" :", 1)[-1] if " :" in capa else capa)
        assert parsed is not None
        assert parsed.nick == "box"
        assert "ping" in parsed.verbs
        assert parsed.psk == "1"

        mal = {"v": 1, "op": "exec", "id": JID, "argv": ["hostname"]}
        blob = seal.dumb_seal_bytes(json.dumps(mal).encode(), key, "#ops", "box", "mallory", JID)
        for ln in seal.dumb_irc_lines(blob, "box", "mallory", JID):
            srv.send_line(f":mallory!u@h PRIVMSG #ops :{ln}")
        time.sleep(2.0)
        with srv._cv:
            priv = [x for x in srv.got if x.startswith("PRIVMSG") and "DUMB v1" in x]
        assert priv == []

        ping = {"v": 1, "op": "ping", "id": "fedcba9876543210"}
        blob2 = seal.dumb_seal_bytes(json.dumps(ping).encode(), key, "#ops", "box", "alice", "fedcba9876543210")
        for ln in seal.dumb_irc_lines(blob2, "box", "alice", "fedcba9876543210"):
            srv.send_line(f":alice!u@h PRIVMSG #ops :{ln}")
        srv.wait_privmsg_contains("DUMB v1", timeout=15)
        with srv._cv:
            wire_lines = [x.split(" :", 1)[1] for x in srv.got if x.startswith("PRIVMSG") and "DUMB v1" in x]
        assert wire_lines
        store = seal.FragmentStore()
        got = None
        for ln in wire_lines:
            parsed_d = wire.parse_dumb_line(ln)
            assert parsed_d is not None
            got = store.add(parsed_d) or got
        assert got is not None
        pt = json.loads(seal.dumb_open_bytes(seal.b64d(got), key, "#ops", "alice", "box", "fedcba9876543210").decode())
        assert pt["ok"] is True
        assert pt["op"] == "ping"
    finally:
        srv.stop()
        proc.kill()
        try:
            proc.wait(timeout=5)
        except Exception:
            pass
