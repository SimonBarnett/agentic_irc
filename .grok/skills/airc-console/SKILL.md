---
name: airc-console
description: >
  Installable airc console Windows service: nick console on #{machinename},
  silent in channel, authenticated PRIVMSG piped to a per-user shell. Use when
  Simon says airc console service, Install-AircConsole, MSI, UAC elevate,
  FR #253, FR #256, FR #259, issue #305, PSScriptRoot empty, Start-AircConsole
  Split-Path, mapped P: download, not digitally signed, or /airc-console.
---

# airc console (FR #253)

Foundation: harvest-agent-skills -> https://github.com/SimonBarnett/agentic_irc

## What it is

Windows service (NSSM `AircConsole`) that keeps IRC nick
**`console-<machinename>`** (e.g. `console-flamingo`) on **`#{COMPUTERNAME}`**.
Bare nick `console` collides on shared Ergo (433) when another box holds it
(issue #286). Silent in the shop channel. Authenticated users PRIVMSG the
console nick; each line is piped to that user's shell session; stdout returns
in Query only.

Not Mode 3 / DUMB PSK. Not Jeeves. Not a talk seat. No `#bobiverse`.

## Install

**Issue #305 (preferred):** install the single **`airc-console-<ver>.msi`**
(per-machine UAC -> `C:\ai\airc-console` -> elevated `Install-AircConsole.cmd`).

**FR #256:** do not run the `.ps1` by path under Restricted/AllSigned — use the
`.cmd` wrapper (Unblock-File + `-ExecutionPolicy Bypass`).

**Issue #305:** `Install-AircConsole.ps1` **self-elevates** (`Start-Process -Verb RunAs`)
when not already admin. Do not use `#Requires -RunAsAdministrator` (that fails
with no UAC prompt).

**FR #259:** install from a **local** tree (`C:\ai\airc-console`). NSSM Path /
Application must be `powershell.exe`, not `Start-AircConsole.ps1`. A mapped
`P:\download\...` Path reproduces empty `$PSScriptRoot` under `[CmdletBinding()]`.

**Issue #266:** release MSI **bundles** `third_party/nssm/win64/nssm.exe`. Install
does not need `C:\ai\ergo\nssm.exe` on the client. Prefer `Install-AircConsole.cmd`
from the installed tree (keeps scripts + third_party together).

**Issue #273:** install **removes** any existing `AircConsole` service then
registers from the current tree. Stopping an already-stopped service must not
fail the script (`nssm` stderr under `$ErrorActionPreference Stop`).

**Issue #277 / #294:** unattended end state is **service Running**. Install copies
release `config/ergo.password` -> `~\.airc-console\ergo.password` (clients need
no `~\.grok`), mints NickServ GUID if needed, then `Start-Service`. Use
`-NoStart` only to skip the start. Never invent the Ergo server secret.

**Issue #282:** LocalSystem has **no** user `PATH`. Install resolves absolute
`python.exe` and passes `-Python` in NSSM AppParameters. Without that, the
service loops on `python.exe not on PATH` and never joins IRC.

```bat
scripts\Install-AircConsole.cmd
```

Or explicit Bypass:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Install-AircConsole.ps1
Get-Service AircConsole
```

Foreground: `Start-AircConsole.cmd -Operators Simon`

Selftest: `python scripts/airc_console_service.py --selftest`

## Release

`Pack-AircConsoleRelease.ps1` -> **`dist/airc-console-<ver>.msi`** (+ `.sha256`),
including NSSM via `Fetch-Nssm.ps1` and WiX via `Fetch-Wix.ps1` (issue #305).
CI workflow `airc-console-release.yml` publishes rolling tag `airc-console` and
immutable `airc-console-v<ver>` (MSI only).

## Auth CAST IRON

Empty operators **and** accounts -> refuse start. Prefer account-tag when
`--require-account` / `--accounts` set (FR #230 map).

**NickServ (#271):** first start mints a GUID into
`~\.airc-console\console.password` and reuses it. Do not ask the operator to
invent one.

**Ergo server PASS (#294):** shipped in the MSI as `config/ergo.password`, then
`~\.airc-console\ergo.password` after Install. Packer uses
`AIRC_PACK_ERGO_PASSWORD` / packer `connect.password`. Never invent; never send
the NickServ GUID as server `PASS`.

**Issue #289:** `operators.txt` must be UTF-8 **without BOM**. PS 5.1 `Set-Content -Encoding utf8` writes BOM and nick `simon` fails auth. Install rewrites; `load_operators` uses utf-8-sig.

**Issue #298:** auto-reconnect on connection loss (backoff reset after good session; idle keepalive PING). Answers CTCP PING and `ping flam*` (NOTICE pong) without operator auth.

**Issue #302:** any `bob-{machinename}` fleet nick may use the console (machine name varies; already authenticated). Install also seeds `bob-<COMPUTERNAME>` into operators.txt.
