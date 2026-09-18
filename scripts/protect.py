"""File ACL (Windows icacls / Unix 0600) and identity-at-rest (DPAPI on NT)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

MAGIC = b"AIRC1"


class ProtectError(Exception):
    pass


def protect_path(path: Path) -> None:
    path = Path(path)
    if os.name == "nt":
        user = os.environ.get("USERNAME") or "Administrators"
        cmd = [
            "icacls",
            str(path),
            "/inheritance:r",
            "/grant:r",
            "NT AUTHORITY\\SYSTEM:(F)",
            "/grant:r",
            "BUILTIN\\Administrators:(F)",
            "/grant:r",
            f"{user}:(F)",
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            err = (r.stderr or r.stdout or f"icacls exit {r.returncode}").strip()
            sys.stderr.write(err + "\n")
            raise ProtectError(f"icacls exit {r.returncode}")
        return
    try:
        os.chmod(path, 0o600 if path.is_file() else 0o700)
    except OSError as e:
        raise ProtectError(f"chmod failed: {e}") from e


def _dpapi_protect(data: bytes) -> bytes:
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    in_buf = ctypes.create_string_buffer(data)
    blob_in = DATA_BLOB(len(data), ctypes.cast(in_buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    if not crypt32.CryptProtectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    ):
        raise OSError("CryptProtectData failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def _dpapi_unprotect(data: bytes) -> bytes:
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    in_buf = ctypes.create_string_buffer(data)
    blob_in = DATA_BLOB(len(data), ctypes.cast(in_buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    if not crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    ):
        raise OSError("CryptUnprotectData failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def write_secret_bytes(path: Path, data: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        path.write_bytes(MAGIC + _dpapi_protect(data))
    else:
        path.write_bytes(data)
    protect_path(path)


def read_secret_bytes(path: Path) -> bytes:
    raw = Path(path).read_bytes()
    if raw.startswith(MAGIC):
        return _dpapi_unprotect(raw[len(MAGIC) :])
    return raw


if sys.platform == "win32":
    pass
