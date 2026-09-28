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

Foundation: harvest-agent-skills â†’ https://github.com/SimonBarnett/agentic_irc

## What it is

Windows service (NSSM `AircConsole`) that keeps IRC nick
**`console-<machinename>`** (e.g. `console-flamingo`) on **`#{COMPUTERNAME}`**.
Bare nick `console` collides on shared Ergo (433) when another box holds it
(issue #286). Silent in the shop channel. Authenticated users PRIVMSG the
console nick; each line is piped to that user's shell session; stdout returns
in Query only.

Not Mode 3 / DUMB PSK. Not Jeeves. Not a talk seat. No `#bobiverse`.

## Install

**FR #256:** do not run the `.ps1` by path under Restricted/AllSigned â€” use the
`.cmd` wrapper (Unblock-File + `-ExecutionPolicy Bypass`).

**FR #259:** install from a **local** tree (`C:\ai\airc-console`). NSSM Path /
Application must be `powershell.exe`, not `Start-AircConsole.ps1`. A mapped
`P:\download\â€¦` Path reproduces empty `$PSScriptRoot` under `[CmdletBinding()]`.

**Issue #266:** release zip **bundles** `third_party/nssm/win64/nssm.exe`. Install
does not need `C:\ai\ergo\nssm.exe` on the client. Prefer `Install-AircConsole.cmd`
from the unpacked release (keeps scripts + third_party together).

**Issue #273:** install **removes** any existing `AircConsole` service then
registers from the current tree. Stopping an already-stopped service must not
fail the script (`nssm` stderr under `$ErrorActionPreference Stop`).

**Issue #277:** unattended end state is **service Running**. Install copies
fleet `~\.grok\ergo\connect.password` â†’ `~\.airc-console\ergo.password` (for
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

`Pack-AircConsoleRelease.ps1` â†’ `dist/airc-console-<ver>.zip` (+ `.sha256`),
including NSSM via `Fetch-Nssm.ps1`. CI workflow `airc-console-release.yml`
publishes rolling tag `airc-console` and immutable `airc-console-v<ver>`.

## Auth CAST IRON

Empty operators **and** accounts â†’ refuse start. Prefer account-tag when
`--require-account` / `--accounts` set (FR #230 map).

**NickServ (#271):** first start mints a GUID into
`~\.airc-console\console.password` and reuses it. Do not ask the operator to
invent one.

**Ergo server PASS (#294):** shipped in the zip as `config/ergo.password`, then
`~\.airc-console\ergo.password` after Install. Packer uses
`AIRC_PACK_ERGO_PASSWORD` / packer `connect.password`. Never invent; never send
the NickServ GUID as server `PASS`.

**Issue #289:** `operators.txt` must be UTF-8 **without BOM**. PS 5.1 `Set-Content -Encoding utf8` writes BOM and nick `simon` fails auth. Install rewrites; `load_operators` uses utf-8-sig.

