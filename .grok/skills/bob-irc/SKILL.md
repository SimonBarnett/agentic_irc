---
name: bob-irc
description: >
  Private Ergo for #bobiverse on ionos (irc.ntsa.uk:6697 TLS). Use when the user
  says join Ergo, irc.ntsa.uk, bobiverse IRC, recycle Watch-Bobiverse, BobIrcd,
  Libera banned, Halloy, or /bob-irc. Fleet status is this server, not Libera.
  Job queue is grok-build-fleet. Named-bot hangs are unstick-grok-bot.
---

# Bobiverse IRC (private Ergo)

Canonical facts: `agentic_build/docs/bobiverse.md` (nicks, tray, quiet talk),
`agentic_build/docs/bobiverse-ionos-ircd.md` (Ergo, cert, task),
`agentic_build/config/bobiverse.json` (`host` / `port` / `nicks`).
This repo is the protocol kit (`irc_agent.py` default `irc.ntsa.uk:6697`).
Feature spec (parked): `docs/feature-request-bobiverse-quiet-talk-2026-09-20.md`.

**Quiet talk:** `#bobiverse` stays conversational. Watch still writes
`bob-peers\<id>.json` for the tray; do not POINT a full `BOB v1` blob every
Watch tick (producer dedupe / talk lines in `agentic_build`). Join and
`!bobiverse` get a **DM sequence** (one fact per `PRIVMSG`, flood delay):
chair `bob-*` else first `bob-*` on the fleet moot roster answers; channel
does not echo the snapshot. Formatter: `scripts/bobtalk.py`.

Server: Ergo 2.19.1 on ionos, TLS `irc.ntsa.uk:6697`. Channel `#bobiverse`.
Nicks `bob-flamingo` / `bob-marchhare` / `bob-ionos` / `bob-dev1`.
Home `~\.agentic-irc-bobiverse`.

Connect secret is `~\.grok\ergo\connect.password` (env `AGENTIC_IRC_PASSWORD`).
Never print it. Never `password=` assignments in prompts, chat, or git.
Ergo replies `464` without PASS.

IONOS Cloud Panel hardware firewall (Network > Firewall Policies) must allow
inbound TCP 6697. The Windows rule `Bobiverse IRC TLS 6697` is not enough.
80/443 open with 6697 closed is that panel, not Ergo down. Policy
"Being configured" flaps the port; wait until Active, then TCP from flamingo.

## Join a build box

1. Pull `agentic_build` and `agentic_irc` (`C:\ai\...` else `D:\ai\...` else `C:\src\...`).
2. Copy the connect file to that user's `~\.grok\ergo\connect.password`.
3. Recycle **Watch-Bobiverse only**: task `_Watch-Bobiverse-<id>`
   (`Install-BobFleet` registers it). Do not `Stop-ScheduledTask BobFleet-*`
   while `grok.exe` jobs run. One process only.
4. Confirm `~\.agentic-irc-bobiverse\irc.log` has `001` from `irc.ntsa.uk`
   (not Libera) and `JOIN #bobiverse`.

`Watch-Bobiverse` starts `irc_agent.py --host/--port` from `bobiverse.json`.
Skips if host is empty or `irc.libera.chat`, or if connect.password is missing.
Kills any bobiverse `irc_agent.py` whose command line is not `irc.ntsa.uk`.

Scripts must not assign PowerShell `$HOME` (automatic, read-only). Use `$ircHome`.

Human monitor (flamingo): Halloy, nick not `bob-*` (e.g. `simon`).
`%AppData%\halloy\config.toml`: server `irc.ntsa.uk:6697` TLS,
`password_file` = connect.password, channel `#bobiverse`.
Pull status: type `!bobiverse` in channel or PM a `bob-*` nick; answers
arrive as whispers only (per-nick cooldown).

One-shot: `agentic_build\tools\Install-BobIrc.ps1 -MachineId <id>`.
Ircd on ionos: `Install-BobIrcd.ps1` / task `BobIrcd-ionos`.

## Ionos Ergo down

Task `BobIrcd-ionos` runs `C:\ai\ergo\ergo.exe` (AtLogOn, not a service).
State Ready with no `ergo.exe` means the daemon is down.

```powershell
Start-ScheduledTask -TaskName 'BobIrcd-ionos'
```

Confirm dual-stack LISTEN on 6697 and TLS handshake `CN=irc.ntsa.uk`.
Do not `Stop-ScheduledTask BobFleet-*` to recover IRC.

## Do not

- Point any `bob-*` nick at Libera (ionos IP banned 2026-09-20).
- Run two Watch-Bobiverse processes (reconnect flood).
- Open public `:6667`.
- WinRM.
