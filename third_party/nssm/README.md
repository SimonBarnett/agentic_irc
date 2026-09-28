# NSSM (bundled for airc-console)

**FR #266:** field installs must not require `C:\ai\ergo\nssm.exe`.

| Path | Notes |
|------|--------|
| `win64/nssm.exe` | NSSM 2.24 64-bit (same binary historically used under `C:\ai\ergo\nssm.exe` on fleet boxes) |

Upstream: https://nssm.cc/ — Non-Sucking Service Manager.

`Install-AircConsole.ps1` resolution order:

1. `third_party/nssm/win64/nssm.exe` beside the unpacked release (preferred)
2. `C:\ai\ergo\nssm.exe` (legacy fleet path)
3. `nssm.exe` on PATH
