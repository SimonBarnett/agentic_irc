from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import dumb_agent
import moot_thin_proto as thin
import seal
import wire

FIX = Path(__file__).resolve().parent / "fixtures" / "mode3"
ROOT = Path(__file__).resolve().parents[1]
JID = "0123456789abcdef"


def _exe() -> str | None:
    env = os.environ.get("AIRC_MOOT_THIN_EXE")
    if env and Path(env).exists():
        return env
    cand = ROOT / "src" / "moot_thin" / "airc-moot-thin.exe"
    if cand.exists():
        return str(cand)
    return None


def test_config_parse_ini_and_cli_override():
    text = (FIX / "config_ok.ini").read_text(encoding="utf-8")
    ini = thin.parse_ini(text)
    cfg = thin.merge_config(ini, None)
    thin.validate_config(cfg)
    assert cfg.nick == "thin-box"
    assert cfg.channel == "#ops"
    assert cfg.moot_id == JID
    assert "alice" in thin.operators_set(cfg.operators)
    argv = thin.parse_argv(["--nick", "other-box", "--operators", "cm-bob"])
    cfg2 = thin.merge_config(ini, argv)
    thin.validate_config(cfg2)
    assert cfg2.nick == "other-box"
    assert thin.operators_set(cfg2.operators) == {"cm-bob"}


def test_empty_operators_refused():
    cfg = thin.ThinConfig(
        nick="thin-box",
        channel="#ops",
        moot_id=JID,
        home=".",
        allow_path=".",
        operators="",
    )
    with pytest.raises(ValueError, match="operators"):
        thin.validate_config(cfg)
    with pytest.raises(ValueError, match="operators"):
        thin.require_operators("  ,  ")


def test_moot_join_golden():
    want = (FIX / "moot_join.txt").read_text(encoding="utf-8").strip()
    assert thin.moot_join_line(JID) == want
    parsed = wire.parse_moot_line(want)
    assert parsed is not None
    assert parsed.verb == "JOIN"
    assert parsed.moot_id == JID


def test_capa_line_shape():
    line = thin.capa_line("thin-box", r"C:\jail", True)
    p = wire.parse_capa_line(line)
    assert p is not None
    assert p.nick == "thin-box"
    assert "exec" in p.verbs
    assert p.psk == "1"


def test_aesgcm_vector_matches_seal():
    vec = json.loads((FIX / "aesgcm_vector.json").read_text(encoding="utf-8"))
    key = bytes.fromhex(vec["key_hex"])
    blob = bytes.fromhex(vec["blob_hex"])
    pt = seal.dumb_open_bytes(blob, key, vec["channel"], vec["to_nick"], vec["from_nick"], vec["msg_id"])
    assert pt.decode("utf-8") == vec["plaintext"]
    job = json.loads(pt)
    assert job["op"] == "ping"
    assert job["id"] == JID


def test_unknown_operator_drop_no_wire_intent(tmp_path):
    job = json.loads((FIX / "job_exec.json").read_text(encoding="utf-8"))
    ops = {"alice"}
    assert thin.emit_result_on_wire("mallory", ops) is False
    assert thin.emit_result_on_wire("alice", ops) is True
    out = thin.run_job(job, operators=ops, from_nick="mallory", allow_path=tmp_path, home=tmp_path)
    assert out["ok"] is False
    assert out["error"] == "operator"


def test_jail_refuse(tmp_path):
    drop = tmp_path / "drop"
    drop.mkdir()
    job = {"v": 1, "op": "get", "id": JID, "path": str(drop / ".." / "Windows" / "win.ini")}
    out = thin.run_job(job, operators={"alice"}, from_nick="alice", allow_path=drop, home=tmp_path)
    assert out["ok"] is False
    assert out["error"] == "jail"
    job2 = {"v": 1, "op": "get", "id": JID, "path": r"\\server\share\x"}
    out2 = thin.run_job(job2, operators={"alice"}, from_nick="alice", allow_path=drop, home=tmp_path)
    assert out2["error"] == "jail"


def test_exec_stdout_rc_framing(tmp_path):
    def runner(argv, cwd, timeout):
        return 0, "ionos-box\n", ""

    job = json.loads((FIX / "job_exec.json").read_text(encoding="utf-8"))
    job["_runner"] = runner
    out = thin.run_job(job, operators={"alice"}, from_nick="alice", allow_path=tmp_path, home=tmp_path)
    assert out["op"] == "exec"
    assert out["ok"] is True
    assert out["rc"] == 0
    assert out["stdout"] == "ionos-box\n"
    assert out.get("truncated") is False


def test_truncation_flag_and_spill(tmp_path):
    big = "B" * 9000

    def runner(argv, cwd, timeout):
        return 0, big, "e"

    job = {"v": 1, "op": "exec", "id": JID, "argv": ["hostname"], "_runner": runner}
    out = thin.run_job(job, operators={"alice"}, from_nick="alice", allow_path=tmp_path, home=tmp_path)
    assert out["truncated"] is True
    assert len(out["stdout"]) + len(out["stderr"]) <= 8192
    spill = tmp_path / "dumb" / "results" / f"{JID}.txt"
    assert big in spill.read_text(encoding="utf-8")


def test_version_sync():
    ver = (ROOT / "src" / "moot_thin" / "VERSION").read_text(encoding="utf-8").strip()
    main = (ROOT / "src" / "moot_thin" / "main.c").read_text(encoding="utf-8")
    assert f'"{ver}"' in main
    assert ver == "0.2.0"


def test_live_tls_contracts_in_source():
    """A5 live smoke: CAP LS without CAP END stalls Libera 001; Schannel must keep incomplete tokens."""
    main = (ROOT / "src" / "moot_thin" / "main.c").read_text(encoding="utf-8")
    tls = (ROOT / "src" / "moot_thin" / "irc_tls.c").read_text(encoding="utf-8")
    assert "CAP END" in main
    assert "ISC_REQ_USE_SUPPLIED_CREDS" in tls
    assert "SEC_I_INCOMPLETE_CREDENTIALS" in tls
    assert "SEC_E_INCOMPLETE_MESSAGE" in tls


def test_release_docs_locked_defaults():
    rel = (ROOT / "docs" / "mode3-release.md").read_text(encoding="utf-8")
    spike = (ROOT / "docs" / "mode3-tls-spike.md").read_text(encoding="utf-8")
    readme = (ROOT / "src" / "moot_thin" / "README.md").read_text(encoding="utf-8")
    assert "mode3-thin" in rel
    assert "airc-moot-thin-v" in rel
    assert "Win95 cannot be claimed" in spike or "No claim that Win95" in spike
    assert "does **not** claim a Win95 pass" in readme or "not claim" in readme.lower()


@pytest.mark.skipif(_exe() is None, reason="airc-moot-thin.exe not built")
def test_c_exe_selftest():
    exe = _exe()
    r = subprocess.run([exe, "--selftest"], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "selftest ok" in (r.stdout or "")


@pytest.mark.skipif(_exe() is None, reason="airc-moot-thin.exe not built")
def test_c_exe_empty_operators(tmp_path):
    exe = _exe()
    r = subprocess.run(
        [
            exe,
            "--offline",
            "--nick",
            "box",
            "--channel",
            "#ops",
            "--moot",
            JID,
            "--home",
            str(tmp_path),
            "--allow-path",
            str(tmp_path),
            "--operators",
            "",
            "--from-nick",
            "alice",
            "--job-in",
            str(FIX / "job_ping.json"),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode != 0
    text = (r.stdout or "") + (r.stderr or "")
    assert "operators" in text.lower()


@pytest.mark.skipif(_exe() is None, reason="airc-moot-thin.exe not built")
def test_c_exe_offline_operator_drop(tmp_path):
    exe = _exe()
    outp = tmp_path / "r.json"
    r = subprocess.run(
        [
            exe,
            "--offline",
            "--nick",
            "box",
            "--channel",
            "#ops",
            "--moot",
            JID,
            "--home",
            str(tmp_path),
            "--allow-path",
            str(tmp_path),
            "--operators",
            "alice",
            "--from-nick",
            "mallory",
            "--job-in",
            str(FIX / "job_exec.json"),
            "--job-out",
            str(outp),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    doc = json.loads(outp.read_text(encoding="utf-8"))
    assert doc["ok"] is False
    assert doc["error"] == "operator"


@pytest.mark.skipif(_exe() is None, reason="airc-moot-thin.exe not built")
def test_c_exe_selfheal_omits_nick_home(tmp_path):
    exe = _exe()
    outp = tmp_path / "r.json"
    r = subprocess.run(
        [
            exe,
            "--offline",
            "--channel",
            "#ops",
            "--moot",
            JID,
            "--operators",
            "alice",
            "--from-nick",
            "alice",
            "--job-in",
            str(FIX / "job_ping.json"),
            "--job-out",
            str(outp),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    doc = json.loads(outp.read_text(encoding="utf-8"))
    assert doc["ok"] is True
    assert doc["op"] == "ping"


@pytest.mark.skipif(_exe() is None, reason="airc-moot-thin.exe not built")
def test_c_exe_missing_channel_one_line(tmp_path):
    exe = _exe()
    r = subprocess.run(
        [
            exe,
            "--offline",
            "--nick",
            "box",
            "--moot",
            JID,
            "--home",
            str(tmp_path),
            "--allow-path",
            str(tmp_path),
            "--operators",
            "alice",
            "--from-nick",
            "alice",
            "--job-in",
            str(FIX / "job_ping.json"),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode != 0
    text = (r.stdout or "") + (r.stderr or "")
    assert "channel" in text.lower()
    assert "usage:" not in text.lower()


@pytest.mark.skipif(_exe() is None, reason="airc-moot-thin.exe not built")
def test_c_exe_selftest_zero_config_lines():
    exe = _exe()
    r = subprocess.run([exe, "--selftest"], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    out = r.stdout or ""
    assert "self-heal nick=" in out
    assert "sibling ini kept nick=keep-me" in out
    assert "pin wrap ok" in out
    assert "pin mismatch refused" in out
    assert "pair grant operators=alice" in out


def test_sanitize_hostname_and_self_heal():
    assert thin.sanitize_hostname("WALRUS") == "walrus"
    assert thin.sanitize_hostname("2012-BOX") == "n2012-box"
    assert thin.sanitize_hostname("!!!") == "thin-box"
    longn = thin.sanitize_hostname("A" * 40)
    assert len(longn) <= 32
    cfg = thin.merge_self_heal(
        {"channel": "#ops", "nick": "keep-me"},
        {"once": True},
        exe_dir=r"C:\airc",
        hostname="WALRUS",
    )
    assert cfg.nick == "keep-me"
    assert cfg.home == r"C:\airc"
    assert cfg.allow_path.lower().endswith("jail")
    cfg2 = thin.merge_self_heal(None, None, exe_dir=r"C:\airc", hostname="WALRUS")
    assert cfg2.nick == "walrus"
    assert cfg2.hello == "walrus-online"


def test_pin_wrap_and_grant_roundtrip():
    vec = json.loads((FIX / "pin_wrap_vector.json").read_text(encoding="utf-8"))
    wrap = thin.wrap_key(vec["pin"], vec["pair_id"], vec["channel"], vec["moot_id"])
    assert wrap.hex() == vec["wrap_key_hex"]
    bad = thin.wrap_key("000000", vec["pair_id"], vec["channel"], vec["moot_id"])
    hello = thin.pair_hello_seal(wrap, vec["channel"], vec["moot_id"], vec["pair_id"], vec["thin_nick"])
    assert thin.pair_hello_open(wrap, vec["channel"], vec["moot_id"], vec["pair_id"], hello) == vec["thin_nick"]
    with pytest.raises(Exception):
        thin.pair_hello_open(bad, vec["channel"], vec["moot_id"], vec["pair_id"], hello)
    psk = bytes.fromhex(vec["psk_hex"])
    grant = thin.pair_grant_seal(
        wrap, vec["channel"], vec["moot_id"], vec["pair_id"], vec["thin_nick"], vec["chair_nick"], psk
    )
    got, chair, moot = thin.pair_grant_open(
        wrap, vec["channel"], vec["moot_id"], vec["pair_id"], vec["thin_nick"], grant
    )
    assert got == psk
    assert chair == vec["chair_nick"]
    assert moot == vec["moot_id"]
    ops = thin.operators_add("", chair)
    assert "alice" in thin.operators_set(ops)
    offer = thin.pair_offer_line(vec["moot_id"], vec["pair_id"], 1710000000)
    assert offer.startswith("PAIR v1 OFFER ")
    assert "1710000000" in offer


def test_zero_config_docs_z0_z8():
    doc = (ROOT / "docs" / "mode3-zero-config-2026-09-19.md").read_text(encoding="utf-8")
    for zid in ("Z0", "Z1", "Z2", "Z3", "Z4", "Z5", "Z6", "Z7", "Z8"):
        assert zid in doc
    assert "state machine" in doc.lower() or "WAIT_HELLO" in doc
    low = doc.lower()
    assert "win95" in low
    assert "not claimed" in low or "still not claimed" in low
    assert "not** ready for human uat" in low or "not ready for human uat" in low
    assert "cleartext" in low
    src = (ROOT / "src" / "moot_thin" / "main.c").read_text(encoding="utf-8")
    assert "PAIR v1" in src or "pair.h" in src
    assert "Does not claim Windows 95 TLS" in src


def test_pairing_validate_skips_operators_unattended_still_refuses():
    cfg = thin.ThinConfig(
        nick="walrus",
        channel="#airc-moot",
        home=".",
        allow_path=".",
        pairing=True,
        pin="482917",
    )
    thin.validate_config(cfg)
    with pytest.raises(ValueError, match="operators"):
        thin.validate_config(
            thin.ThinConfig(
                nick="box",
                channel="#ops",
                moot_id=JID,
                home=".",
                allow_path=".",
                operators="",
            )
        )


def test_default_bins_powershell_optional():
    assert "cmd.exe" in dumb_agent.DEFAULT_BINS
    assert "hostname.exe" in dumb_agent.DEFAULT_BINS
    src = (ROOT / "src" / "moot_thin" / "jail.c").read_text(encoding="utf-8")
    assert "powershell_present" in src
    assert "cmd.exe" in src
