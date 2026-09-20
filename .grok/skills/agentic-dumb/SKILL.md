---
name: agentic-dumb
description: >
  Drive an ancient host (Server 2012) from IRC. Connector only, no LLM. Use for
  Server 2012, dumb agent, cmd.exe on the other box. Install only on machines you administer.
---

# agentic-dumb

Not an agent. Connectors share the same PSK DUMB v1 protocol:

- **Python reference:** `scripts/dumb_agent.py` joins the channel (stdlib socket+ssl), announces CAPA on join and every 10 minutes, and runs **allowlisted** ping/sysinfo/exec/get/put from `--operators` only.
- **net45 adapter:** `src/dumb_dotnet/airc-dumb.exe` (TcpClient + SslStream TLS 1.2). Same CAPA, jobs, jail, and wire rules. Python remains the protocol reference.
- **Mode 3 thin CLI:** `src/moot_thin/airc-moot-thin.exe`. Click the exe / enter PIN (chair `airc-moot-thin.exe --chair`). `--pin` for scripting. `--key` still works for air-gap. Empty `--operators` refused for unattended installs. Win95 TLS is **not** claimed. See `docs/mode3-zero-config-2026-09-19.md`.

Unknown operators: no exec, no result ciphertext on the channel. Truncated exec stdout/stderr spills to `dumb/results/<id>.txt` with `truncated: true`. Empty `--operators` is refused.

Generate PSK **off-channel** (`python scripts/seal.py dumb-key`). Copy `connector.key` by RDP/USB. Never print it. Compare sha256 fingerprints out of band. The file may be raw 32 bytes or `AIRC1`+DPAPI.

`--operators` is required. Jail `--allow-path` (default `C:\agent-drop`). Default bins: cmd.exe, powershell.exe, hostname.exe, ipconfig.exe, whoami.exe.

```
python scripts/dumb_ctl.py ping --home H --channel '#ops' --from-nick ME --to srv2012-box
python scripts/dumb_ctl.py exec --home H --from-nick ME --to srv2012-box --argv hostname
```

TLS 1.2 preflight on Server 2012: if SslException, enable SchUseStrongCrypto (Microsoft docs). Do not dump connector.key. Do not exec if operators empty.

Build the net45 exe: `src/dumb_dotnet/build.bat` or `msbuild airc-dumb.csproj /p:Configuration=Release /p:TargetFrameworkVersion=v4.5`. No runtime NuGet for crypto. Use `airc-dumb.cmd` as the scheduled-task wrapper. `--tls-insecure` is lab/offline only. Offline pytest: `DOTNET_DUMB_EXE`. Not ready for human UAT (no live Server 2012 claim from this tree). Production fleet IRC is Ergo `irc.ntsa.uk:6697` (Python/net45 default). Pass `--host` for any other network.

Scheduled task (operator fills paths):

```
schtasks /create /tn airc-dumb /sc onstart /ru USER /tr "C:\airc-dumb\airc-dumb.cmd"
```
