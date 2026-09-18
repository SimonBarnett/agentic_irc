from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import protect  # noqa: E402


def test_icacls_exit_5_is_visible(monkeypatch, tmp_path: Path, capsys):
    monkeypatch.setattr(protect.os, "name", "nt")

    def fake_run(cmd, capture_output=True, text=True):
        return SimpleNamespace(returncode=5, stderr="Access is denied.\n", stdout="")

    monkeypatch.setattr(protect.subprocess, "run", fake_run)
    f = tmp_path / "x"
    f.write_text("n")
    with pytest.raises(protect.ProtectError, match="icacls exit 5"):
        protect.protect_path(f)
    err = capsys.readouterr().err
    assert "Access is denied" in err or "5" in err


@pytest.mark.skipif(os.name == "nt", reason="Unix chmod path")
def test_chmod_failure_raises(monkeypatch, tmp_path: Path):
    def boom(path, mode):
        raise OSError("erofs")

    monkeypatch.setattr(protect.os, "chmod", boom)
    with pytest.raises(protect.ProtectError, match="chmod failed"):
        protect.protect_path(tmp_path / "x")


@pytest.mark.skipif(os.name != "nt", reason="DPAPI is Windows-only")
def test_dpapi_roundtrip(tmp_path: Path):
    p = tmp_path / "ident"
    protect.write_secret_bytes(p, b'{"v":1}')
    assert p.read_bytes().startswith(protect.MAGIC)
    assert protect.read_secret_bytes(p) == b'{"v":1}'
