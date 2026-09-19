---
name: agentic-dumb
description: >
  Drive an ancient host (Server 2012) from IRC. Connector only, no LLM. Use for
  Server 2012, dumb agent, cmd.exe on the other box. Install only on machines you administer.
---

# agentic-dumb

Not an agent. `scripts/dumb_agent.py` joins the channel (stdlib socket+ssl), announces CAPA on join and every 10 minutes, and runs **allowlisted** ping/sysinfo/exec/get/put from `--operators` only. Unknown operators: no exec, no result on the channel. Truncated exec stdout/stderr spills to `dumb/results/<id>.txt` with `truncated: true`.

Generate PSK **off-channel** (`python scripts/seal.py dumb-key`). Copy `connector.key` by RDP/USB. Never print it. Compare sha256 fingerprints out of band.

`--operators` is required. Jail `--allow-path` (default `C:\agent-drop`). Default bins: cmd.exe, powershell.exe, hostname.exe, ipconfig.exe, whoami.exe.

```
python scripts/dumb_ctl.py ping --home H --channel '#ops' --from-nick ME --to srv2012-box
python scripts/dumb_ctl.py exec --home H --from-nick ME --to srv2012-box --argv hostname
```

TLS 1.2 preflight on Server 2012: if SslException, enable SchUseStrongCrypto (Microsoft docs). Do not dump connector.key. Do not exec if operators empty.

`src/dumb_dotnet` is a net45 **stub** (prints INFO, exits 0) until Phase 5. Python `scripts/dumb_agent.py` is the protocol reference. Build: `msbuild airc-dumb.csproj /p:Configuration=Release /p:TargetFrameworkVersion=v4.5`. Use `airc-dumb.cmd` as the scheduled-task wrapper.

Scheduled task (operator fills paths):

```
schtasks /create /tn airc-dumb /sc onstart /ru USER /tr "C:\airc-dumb\airc-dumb.cmd"
```
