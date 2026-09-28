# airc console (FR #253)

Installable Windows service: IRC nick **`console`** on **`#{machinename}`**.

## Behaviour

- Registers / identifies the `console` nick (password via file or `AIRC_CONSOLE_PASSWORD`)
- JOINs `#{COMPUTERNAME}` (creates channel when the network allows); **silent** in channel
- Direct PRIVMSG from authenticated operators opens a per-user shell session
- PRIVMSG text is piped to that console; stdout returns in Query (never on the shop channel)
- Empty operators/accounts refused

## Install (Windows + NSSM)

Downloaded zips are **unsigned**. Do **not** double-click / invoke the `.ps1`
directly under Restricted/AllSigned — that fails with "not digitally signed"
(FR #256). Use the `.cmd` wrappers (they `Unblock-File` + `-ExecutionPolicy Bypass`):

```bat
REM elevated cmd.exe
Set-Content %USERPROFILE%\.airc-console\operators.txt Simon
scripts\Install-AircConsole.cmd
net start AircConsole
```

Equivalent PowerShell (explicit Bypass):

```powershell
Set-Content $env:USERPROFILE\.airc-console\operators.txt "Simon"
# optional: console.password for NickServ/SASL
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Install-AircConsole.ps1
Start-Service AircConsole
```

Foreground smoke:

```bat
scripts\Start-AircConsole.cmd -SelfTest
scripts\Start-AircConsole.cmd -Operators Simon
```

## Release

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\Pack-AircConsoleRelease.ps1
# -> dist/airc-console-<ver>.zip (+ .sha256)
```

GitHub Actions workflow `airc-console-release.yml` publishes tag `airc-console` (rolling) and immutable `airc-console-v*`.
