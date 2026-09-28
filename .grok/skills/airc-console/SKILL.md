---
name: airc-console
description: >
  Installable airc console Windows service: nick console on #{machinename},
  silent in channel, authenticated PRIVMSG piped to a per-user shell. Use when
  Simon says airc console service, Install-AircConsole, FR #253, FR #256,
  not digitally signed, or /airc-console.
---

# airc console (FR #253)

Foundation: harvest-agent-skills → https://github.com/SimonBarnett/agentic_irc

## What it is

Windows service (NSSM `AircConsole`) that keeps IRC nick **`console`** on
**`#{COMPUTERNAME}`**. Silent in the shop channel. Authenticated users PRIVMSG
`console`; each line is piped to that user's shell session; stdout returns in
Query only.

Not Mode 3 / DUMB PSK. Not Jeeves. Not a talk seat. No `#bobiverse`.

## Install

**FR #256:** do not run the `.ps1` by path under Restricted/AllSigned — use the
`.cmd` wrapper (Unblock-File + `-ExecutionPolicy Bypass`):

```bat
scripts\Install-AircConsole.cmd
net start AircConsole
```

Or explicit Bypass:

```powershell
Set-Content $env:USERPROFILE\.airc-console\operators.txt "Simon"
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Install-AircConsole.ps1
Start-Service AircConsole
```

Foreground: `Start-AircConsole.cmd -Operators Simon`

Selftest: `python scripts/airc_console_service.py --selftest`

## Release

`Pack-AircConsoleRelease.ps1` → `dist/airc-console-<ver>.zip` (+ `.sha256`).
CI workflow `airc-console-release.yml` publishes rolling tag `airc-console`.

## Auth CAST IRON

Empty operators **and** accounts → refuse start. Prefer account-tag when
`--require-account` / `--accounts` set (FR #230 map).
