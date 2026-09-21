# Skill harvest log

## 2026-09-21 — live reportUrl irc.ntsa.uk:80

Digest write URL is `http://irc.ntsa.uk:80/bob/v1/report`. GET 405,
POST 204/200. POST 401 = flamingo secret != ionos `report.secret`.

## 2026-09-21 — create worker before working_on

Webhook create is `merge` with `pid` and no `working_on`. Then POST
`working_on` or `--idle`. `post_working_on.py --create` then
`--working-on`. Do not set the job on a worker that does not exist.

## 2026-09-21 — webhook on worker change or idle

Workers POST `/bob/v1/report` whenever `working_on` changes or they go
idle (`scripts/post_working_on.py`, `--idle` for empty). Skip unchanged.
204 = change, 200 = same. Watch fleet skip-heartbeat remains
agentic_build#141.

## 2026-09-21 — talk nick is {machine}-{pid}

Cursor and Grok use the same nick `{machine}-{pid}` (e.g. `flamingo-17568`).
Not `cursor-*` / `grok-*`. Same JOIN, home, TSR, Query working-on.

## 2026-09-21 — shop nicks, chair-only digest, webhook bind

Talk-seat nick is `{machine}-{pid}` (Cursor and Grok the same) and JOINs
`#bobiverse` plus `#<machine>` (not `#bob-*` rooms). One voice: do not dual-
outbox. Halloy lists only joined rooms; shops are dynamic. Persist
`chairNick` (live: Jeeves) on each `bob-*` home or builders answer
`!bobiverse`. `bobcallback` default bind is loopback; DNS optional; 204
then 200. Query gets `This is what I'm working on`. Skills `bob-irc` +
`agentic-irc`.

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
