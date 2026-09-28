# FR #253 — airc console service

**Issue:** https://github.com/SimonBarnett/agentic_irc/issues/253

## Goal

Installable **airc** service on each Windows box:

1. Connect as nick **`console`**
2. JOIN (create if missing) channel **`#{machinename}`**
3. Register / identify the nick
4. Stay **silent** in the shop channel
5. Per authenticated user: PRIVMSG session → interactive console pipe
6. Only authenticated users may PRIVMSG the console
7. Ship as a **release** zip (+ checksum)

## Acceptance (MVP)

| Gate | Proof |
|------|--------|
| Channel naming | `shop_channel("IONOS") == "#ionos"` |
| Silent channel | Public PRIVMSG on `#{machine}` never answered on-channel |
| Auth gate | Unknown nick → deny reply in Query; operator → pipe |
| Session | Per-nick shell; `.quit` closes |
| Service install | `Install-AircConsole.ps1` registers NSSM `AircConsole` |
| Unsigned download install (FR #256) | `Install-AircConsole.cmd` uses Unblock-File + `-ExecutionPolicy Bypass` |
| Start on mapped drive / CmdletBinding (FR #259) | `Start-AircConsole.ps1` resolves script dir in body — never `$PSScriptRoot` in `param()` defaults |
| Bundled NSSM (issue #266) | Release zip includes `third_party/nssm/win64/nssm.exe`; install does **not** require `C:\ai\ergo\nssm.exe` |
| NickServ GUID (issue #271) | First start mints GUID into `console.password`; reuse next start; Ergo PASS stays separate |
| Release | `Pack-AircConsoleRelease.ps1` builds `dist/airc-console-*.zip` |
| Selftest | `airc_console_service.py --selftest` exit 0 |

## Install notes (FR #259 / #266)

NSSM **Application** must be `powershell.exe` (not the `.ps1`). Prefer a **local** install tree (`C:\ai\airc-console\scripts\…`) over a mapped download drive (`P:\download\…`). Mapped drives + `[CmdletBinding()]` left `$PSScriptRoot` empty in param defaults and crashed `Start-AircConsole.ps1` before Python ran.

**NSSM binary:** the release zip ships `third_party/nssm/win64/nssm.exe` (public domain, https://nssm.cc). `Install-AircConsole.ps1` resolves that path first, then legacy `C:\ai\ergo\nssm.exe`, then `PATH`. Pass `-Nssm` only to override.

Do not name a PowerShell parameter `$Home` (automatic read-only) — launchers use `-ConsoleHome`.

Ergo (`irc.ntsa.uk`) needs a server **`PASS`** before `NICK`/`USER`. That secret
comes from `AIRC_CONSOLE_SERVER_PASSWORD` / `AGENTIC_IRC_PASSWORD` /
`~\.airc-console\ergo.password` / `~\.grok\ergo\connect.password` — **never
invented**.

**NickServ** (issue #271): on first start the client **mints a GUID** into
`~\.airc-console\console.password` and reuses it for REGISTER/IDENTIFY. Operators
do not choose this password. SASL (optional `--sasl`) uses the same GUID.

## Non-goals (this PR)

- Not a fleet talk seat / digester / Mode 3 PIN chair
- No `#bobiverse` presence
- No claim of live human UAT on every box from CI

## Layout

- `scripts/airc_console.py` — offline core
- `scripts/airc_console_service.py` — TLS IRC host
- `scripts/Start-AircConsole.ps1` / `Install-AircConsole.ps1` / `Pack-AircConsoleRelease.ps1`
- `src/airc_console/` — VERSION + README for release staging
- `.grok/skills/airc-console/SKILL.md`
- `tests/test_airc_console_fr253.py`

## Auth

Operators file / CLI nick allowlist. Optional services **account** allowlist via IRCv3 `account-tag` / `AccountMap` (FR #230). Empty operators **and** accounts → refuse start.
