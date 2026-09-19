# Mode 3 OS matrix (A4)

Status of `airc-moot-thin.exe` as of the first Mode 3 ticket. **Not** ready for human UAT. **No IONOS live smoke in this ticket** (A5 is Phase 4).

Compile target: 32-bit Win32 **ANSI** console PE, `_WIN32_WINNT=0x0501`. TLS: Schannel. Jobs: DUMB v1 AES-256-GCM + moot JOIN. Exec: `--operators` allowlist.

| OS | Load PE | TLS 1.2 to Libera | Offline `--selftest` | Live moot+exec | Row |
|---|---|---|---|---|---|
| Windows 95 OSR2 | No (XP-era imports) | No — see [mode3-tls-spike.md](./mode3-tls-spike.md) | n/a | **blocked U1** | do not claim |
| Windows 98 | No | No | n/a | **blocked U1** | do not claim |
| Windows ME | excluded by FR | | | | excluded |
| Windows NT 4 | No | No | n/a | **blocked U1** | do not claim |
| Windows 2000 | Unknown | No official TLS 1.2 | untested | **blocked U1** | untested |
| Windows XP SP3 | Expected (untested here) | No official TLS 1.2 | untested | **blocked U1** | untested load |
| Windows Vista | Likely | TLS 1.2 with updates | untested | untested | untested |
| Windows 7 SP1 | Likely | Possible after KB3140244 | untested | untested | possible |
| Windows 8 / Server 2012 | Expected | Expected | untested on real 2012 | P4 | expected-good |
| Windows 10 / 11 / Server 2022 | Yes on CI builder | Expected | `--selftest` on `windows-latest` | P4 IONOS | builder |
| Windows 11 (IONOS) | This ticket's compile host | Expected | run if exe built locally | **not done this ticket** | no A5 claim |

## How to run on XP+ today (offline / modern)

XP **cannot** be told to open Libera with this binary. On a Win8+ box:

1. Download `airc-moot-thin.exe` + `.sha256` from the `mode3-thin` GitHub Release.
2. Generate a 32-byte connector key **off channel**. On a Mode 2 box: `python scripts/seal.py dumb-key --home <dir>`. Copy `connector.key` via USB/RDP. Compare SHA-256 fingerprint out of band. If the key was written by Python on Windows it starts with `AIRC1` + DPAPI; the thin client will unprotect it on the **same user/machine**. A raw 32-byte file also works (portable across boxes).
3. Copy `airc-moot-thin.ini.example` to `airc-moot-thin.ini`. Fill nick, channel, 16-hex moot id, home, `--allow-path` jail, `--operators` (chair nick). **Do not leave operators empty.**
4. Chair (Python `moot.py` / agent) **OPEN**s the moot first, then start the exe. It JOIN-s the channel, emits `CAPA v1 dumb`, then `MOOT v1 JOIN <id>`.
5. Operator on the allowlist sends a DUMB v1 sealed `exec` (same as Mode 2 `dumb_ctl.py`). Thin client returns stdout/stderr/rc as a sealed DUMB result. Floor alone is **not** enough.

Live IONOS smoke (hostname visible to `cm-bob`) is **Phase 4**, not claimed here.
