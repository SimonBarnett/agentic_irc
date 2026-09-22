# Skill harvest log

## 2026-09-22 — IRC 60s silence: verify connection

If no new `FROM` / `irc.log` write for 60s, assume deaf: recycle
`Start-IrcTsr` + `irc_agent`. `Watch-IrcTsr.ps1` `-SilenceSec 60` poll 30s.
Skills `agentic-irc` + `bob-irc`.

## 2026-09-21 — SEAL key to users + TSR watchdog

Webhook `report.secret`: FILE tier S from ionos to **both** `{machine}-{pid}`
and `bob-<machine>` (flamingo-17568 / bob-flamingo, marchhare-24028 /
bob-marchhare). Skills `agentic-file`, `bob-irc`.

TSR harden: `agentic_build/tools/Watch-IrcTsr.ps1` + `_Watch-IrcTsr-ionos.ps1`
+ logon `IrcTsrWatch-ionos`. Poll 45s; restart if dead, no listen, or runner
>600s. Not Watch-CursorIrc. Skills `agentic-irc`, `bob-irc`.

## 2026-09-21 — FILE tier S report.secret to flamingo

Simon asks on `#bobiverse` / PM: SEAL `~\.grok\bob\report.secret` to
`flamingo-17568` (tier S, AAD `#bobiverse`). Use `filexfer.py --home <ircHome>
offer` (home flag **before** `offer`, not after). PowerShell: use `$ircHome`,
not `$home` (read-only `$HOME`). Skills `agentic-file`, `bob-irc`.

## 2026-09-21 — Ionos webhook IIS + SEAL report secret

`scripts/Install-BobReport.ps1`: `reportUrl` `http://bob.ntsa.uk/bob/v1/report`,
IIS `irc-ntsa` + ARR → `bobcallback` `127.0.0.1:19781`, task `BobReport-ionos`.
`report.secret` must be UTF-8 no BOM. Distribute `BOB_REPORT_SECRET` + URL to
peers via SEAL v2 (`PRIVMSG` outbox lines, newline terminated). `irc_agent`
accepts SEAL on Query PM (not only channel). Skills `bob-irc` + `agentic-irc`.

## 2026-09-21 — Start-IrcTsr.ps1 (fleet)

`agentic_build/tools/Start-IrcTsr.ps1`, `Irc-Tsr-Runner.ps1`,
`_Start-IrcTsr-ionos.ps1`; `Watch-CursorIrc` prefers TSR over bare listen.
Wake: `^AGENT_LOOP_WAKE_irc-tsr`. Skills updated.

## 2026-09-21 — IRC TSR required (no idle)

Listener without notify/wake still goes deaf when the Cursor turn ends.
You must run a TSR to be triggered: `irc_listen.py` + notify_on_output
on `^FROM `. Skills `agentic-irc` + `bob-irc`.

## 2026-09-21 — IRC listener required for responses

Coordinator talk is send-only unless `irc_agent` (DEBUG=1, own home) plus
`scripts/irc_listen.py` stay up. Wake on `FROM nick target text`. Do not
use `\\192.168.1.200\nas\bot.txt` for ionos (VPS cannot see bobnet SMB).
Skills `agentic-irc` + `bob-irc`.

## 2026-09-21 — flamingo Halloy + extra irc_agent vs Watch

Session on flamingo: Halloy nick `simon`; coordinator `cursor-flamingo`
(`~\.agentic-irc-cursor`); Watch `bob-flamingo`. Watch up-check is any
`irc_agent.py` + `bobiverse` + `irc.ntsa.uk`, so the extra nick blocks
respawn of `bob-*`. Recycle the builder process only. `#54` mention ACK
works at `weekly=0`; digest `online` needs shop JOIN / report POST, not
NAMES. Grok-talk LLM stays FR #56. Skills `bob-irc` + `agentic-irc`.

## 2026-09-21 — Ergo service BobIrcd

Ionos ircd is Windows service `BobIrcd` (`Start-Service BobIrcd`), not
task `BobIrcd-ionos`. NSSM + Automatic + LocalSystem. Recovery lives in
`.grok/skills/bob-irc`. `invite-airc` points at that service. Cert
recycle is `C:\ai\ergo\install-cert.ps1` (service, not the old task).

## 2026-09-20 — bob-irc lives here

Fleet Ergo playbook (`irc.ntsa.uk:6697`, connect.password, Watch-Bobiverse
recycle, IONOS hardware firewall TCP 6697, Halloy monitor, BobIrcd start)
harvested into `.grok/skills/bob-irc`. Protocol leaflets stay `agentic-irc`
/ `agentic-moot` / `agentic-file` / `agentic-dumb` / `invite-airc`.
`agentic_build` keeps a stub that points here. `install_skill.py` copies
`bob-irc` SKILL.md (no scripts dump).
