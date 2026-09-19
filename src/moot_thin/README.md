# airc-moot-thin (Mode 3)

Win32 **ANSI** 32-bit console PE. Not an LLM. Not 16-bit DOS. Not the net45 `airc-dumb.exe` connector (that lives in `src/dumb_dotnet/`).

Joins a moot, accepts **DUMB v1** sealed jobs from `--operators`, runs allowlisted bins inside `--allow-path`, returns stdout/stderr/rc.

## Toolchain (primary)

MSVC x86 (Visual Studio 2022 Build Tools / GitHub `windows-latest`):

```
# x86 developer prompt, or GHA ilammy/msvc-dev-cmd arch=x86
cd src\moot_thin
build.bat
airc-moot-thin.exe --selftest
```

Defines: `WINVER=0x0501`, `_WIN32_WINNT=0x0501`, no `UNICODE`. Subsystem CONSOLE. Links `ws2_32 secur32 crypt32 advapi32`.

Optional: MinGW-w64 i686 (`make` / `gcc -m32`).

## WINVER / known floors

| Macro | Value | Meaning |
|---|---|---|
| `WINVER` / `_WIN32_WINNT` | `0x0501` | XP-era SDK surface (Winsock2, Schannel, CryptoAPI) |
| Character set | ANSI (`*A` APIs) | Not Unicode; intended 9x-era *feel*, but **not** a 9x binary |
| Machine | x86 | 32-bit PE |

**Windows 95/98/NT4 will not load this PE.** **Windows ME excluded.** Live Libera needs Schannel TLS 1.2: expected **Windows 8 / Server 2012+**. See `docs/mode3-tls-spike.md`. This README does **not** claim a Win95 pass.

## CLI

```
airc-moot-thin.exe --nick thin-box --channel #ops --moot 0123456789abcdef ^
  --home C:\airc-thin --allow-path C:\airc-thin\jail --operators cm-bob ^
  --key C:\airc-thin\dumb\connector.key
```

`--config airc-moot-thin.ini` may supply the same keys; CLI wins. Empty `--operators` is refused (no exec, no result ciphertext). `--selftest` and `--offline` never open a socket.

## Protocol

- IRC: NICK/USER/JOIN, flood 0.8s, CAPA every 600s, reconnect backoff unless `--once`.
- Moot: `MOOT v1 JOIN <id>` (chair should OPEN first).
- Jobs: DUMB v1 `ping` / `sysinfo` / `exec` / `get` / `put`. AES-256-GCM PSK, AAD `lower(channel)|lower(to)|lower(from)|lower(id)|dumb-v1`.
- Exec bins: `cmd.exe`, `hostname.exe`, `ipconfig.exe`, `whoami.exe` (+ names without `.exe`). `powershell.exe` only if present on the box.
- Jail: path must resolve under `--allow-path`. UNC and `..` escapes refused. Truncation: `truncated: true` and spill `HOME\dumb\results\<id>.txt` over 8192 bytes.

## Secrets

Do not commit keys. Do not print the PSK. Fingerprint = SHA-256 of the 32 raw key bytes (logged as `keyfp=`). `AIRC1`+DPAPI files from Python `protect.py` unprotect on the same Windows user; raw 32-byte files are portable.
