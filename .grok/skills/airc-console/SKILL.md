---
name: airc-console
description: >
  Installable airc console Windows service: nick console on #{machinename},
  silent in channel, authenticated PRIVMSG piped to a per-user shell. Use when
  Simon says airc console service, Install-AircConsole, FR #253, FR #256,
  FR #259, PSScriptRoot empty, Start-AircConsole Split-Path, mapped P: download,
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
`.cmd` wrapper (Unblock-File + `-ExecutionPolicy Bypass`).

**FR #259:** install from a **local** tree (`C:\ai\airc-console`). NSSM Path /
Application must be `powershell.exe`, not `Start-AircConsole.ps1`. A mapped
`P:\download\…` Path reproduces empty `$PSScriptRoot` under `[CmdletBinding()]`.

**Issue #266:** release zip **bundles** `third_party/nssm/win64/nssm.exe`. Install
does not need `C:\ai\ergo\nssm.exe` on the client. Prefer `Install-AircConsole.cmd`
from the unpacked release (keeps scripts + third_party together).

**Issue #273:** install **removes** any existing `AircConsole` service then
registers from the current tree. Stopping an already-stopped service must not
fail the script (`nssm` stderr under `$ErrorActionPreference Stop`).

**Issue #277:** unattended end state is **service Running**. Install copies
fleet `~\.grok\ergo\connect.password` → `~\.airc-console\ergo.password` (for
LocalSystem), mints NickServ GUID if needed, then `Start-Service`. Use
`-NoStart` only to skip the start. Never invent the Ergo server secret.

**Issue #282:** LocalSystem has **no** user `PATH`. Install resolves absolute
`python.exe` and passes `-Python` in NSSM AppParameters. Without that, the
service loops on `python.exe not on PATH` and never joins IRC.

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

`Pack-AircConsoleRelease.ps1` → `dist/airc-console-<ver>.zip` (+ `.sha256`),
including NSSM via `Fetch-Nssm.ps1`. CI workflow `airc-console-release.yml`
publishes rolling tag `airc-console` and immutable `airc-console-v<ver>`.

## Auth CAST IRON

Empty operators **and** accounts → refuse start. Prefer account-tag when
`--require-account` / `--accounts` set (FR #230 map).

**NickServ (#271):** first start mints a GUID into
`~\.airc-console\console.password` and reuses it. Do not ask the operator to
invent one.

**Ergo server PASS:** `AGENTIC_IRC_PASSWORD` / `AIRC_CONSOLE_SERVER_PASSWORD` /
`~\.airc-console\ergo.password` / `~\.grok\ergo\connect.password`. Never invent
the fleet server secret; never send the NickServ GUID as server `PASS`.
