---
name: bob-irc
description: >
  Private Ergo for #bobiverse on ionos (irc.ntsa.uk:6697 TLS). Use when the user
  says join Ergo, irc.ntsa.uk, bobiverse IRC, recycle Watch-Bobiverse, BobIrcd,
  Libera banned, Halloy, shop channel, !bobiverse, or /bob-irc. Fleet status is
  this server, not Libera. Job queue is grok-build-fleet.
---

# Bobiverse IRC (private Ergo)

Canonical facts (do not duplicate the nick table here): `agentic_build/docs/bobiverse.md`,
`agentic_build/config/bobiverse.json` (`host` `irc.ntsa.uk`, `port` 6697, `nicks`, `reportUrl`).
Registry machine id for DEV1 is **`ce-priority-dev1`** → nick `bob-dev1` (alias `dev1`).

Live specs in **this** repo: `docs/feature-request-shop-channel-worker-cc-webhook-2026-09-21.md`
(issue #46 — shop channels, pid workers, write-only callback, `!bobiverse` only),
`docs/feature-request-house-clean-irc-kit-2026-09-21.md` (issue #34),
`docs/multi-agent-one-host.md`, `docs/beacon-v1-2026-09-19.md`. Index: `docs/README.md`.
Do **not** point agents at `mrb-*.pdf`. Do **not** implement `!report` (#36 write path scrubbed).

## Rooms

- Fleet: `#bobiverse` — Bob `/me` lifecycle + working-on. No POINT firehose.
- Shop: `#flamingo` `#marchhare` `#ionos` `#ce-priority-dev1` (`#dev1` same).
  `bob-<id>` JOINs fleet + shop at start. Workers JOIN **shop only**.
- Worker nick: `w-<shortid>-<pid>` (`w-fl-4412`). Key is `flamingo:4412`.
  Home: `~\.agentic-irc-bobiverse\workers\<id>\<pid>`.

## Status read / write

- **Read:** `!bobiverse` / `!bobiverse ?` / `!bobiverse <id>` — **digest chair**
  (`bob-chair` / `AGENTIC_IRC_CHAIR_NICK`) whispers JSON (~60s human / ~120s agent).
  Digest file is **not** HTTP GET. `bob-<machine>` builders do not answer digest.
- **Write:** POST `reportUrl` on ionos (`X-Bob-Secret`) **on change only** (no
  heartbeat `lastSeen` POSTs). See `docs/bob-report-callback-change-only.md`.
  Chair merges into `digest.json`; builders do not fleet-narrate `#bobiverse`.
- **Chair seat:** `scripts/Install-BobChair.ps1` / `irc_agent.py --chair` JOINs
  `#bobiverse` only. MOOT floor chair is separate from digest chair.
- Machines persist (`status`: `I am online` / `I am offline`). Workers are
  deleted on disconnect. Bob drop closes `#<id>` and deletes that box's workers.

## CC

Shop: conversation stdout + `This is what I'm working on: …`
Query with worker, if open: also thinking traces + tool transcripts.
Secrets-shaped lines: drop. Workers never JOIN `#bobiverse`.

## Connect

Server: Ergo on ionos, TLS `irc.ntsa.uk:6697`. Home `~\.agentic-irc-bobiverse`.
Connect secret: `~\.grok\ergo\connect.password` (`AGENTIC_IRC_PASSWORD`).
Never print it. Never `password=` assignments in prompts, chat, or git.
Callback secret: `~\.grok\bob\report.secret` (`BOB_REPORT_SECRET`).

IONOS panel must allow 6697 and the `reportUrl` port. Policy "Being configured"
flaps the port.

## Join a build box

1. Pull `agentic_build` and `agentic_irc`.
2. Copy connect.password (and report.secret on writers).
3. Recycle **Watch-Bobiverse only**. Confirm `001` from `irc.ntsa.uk` and
   `JOIN #bobiverse` plus `JOIN #<id>`.

Coordinator sessions that talk on IRC must run the agentic-irc TSR
(`irc_listen.py` plus notify_on_output / wake on `^FROM `) so they
are triggered. Listener without a wake is idle. Outbox alone is
send-only. Do not use LAN SMB to reach ionos.

Human monitor (flamingo): Halloy nick not `bob-*` (e.g. `simon`).
`%AppData%\halloy\config.toml`: server `irc.ntsa.uk:6697` TLS,
`password_file` = connect.password, channel `#bobiverse`. Type `!bobiverse`.
Address a `bob-*` nick (`@bob-ionos`, `bob-flamingo:`, Query): that seat
ACKs one English line (status + weekly). `weekly=0` still answers
(empty weekly is not deaf; #54). Optional **grok-talk** (LLM listen+reply;
FR #56, Bob stamps UAT) is off by default: set `grok-talk.json`
`{"grok_talk_enabled": true}` or env `AGENTIC_IRC_GROK_TALK=1` on a seat
after UAT; requires `weekly` > 0. Jobs go to `grok-inbox.jsonl`;
completions via `grok-outbox.jsonl` → `outbox.txt`
(`docs/grok-talk-envelope-v1.md`, `scripts/grok_talk_drain.py`).
Watch stays no grok.exe. Recycle Watch-Bobiverse after pull so the
running `irc_agent` loads mention ACK + grok-talk hooks.

`!bobiverse` `online` is shop JOIN / report POST, not NAMES. A box that
only POINTs on `#bobiverse` still shows `I am offline` in the digest.

## Recycle while a second irc_agent is up

Watch `Test-BobiverseIrcAgentUp` is true if **any** `irc_agent.py` command
line has `bobiverse` and `irc.ntsa.uk` (or `127.0.0.1`). A coordinator
nick (`cursor-flamingo`, home `~\.agentic-irc-cursor`) blocks Watch from
starting `bob-<id>`. Recycle the builder only: stop the process whose
`--nick` is `bob-<id>`; start it from the pulled `scripts\irc_agent.py`
with `--home ~\.agentic-irc-bobiverse`. Leave the extra nick running.
Do not `Stop-ScheduledTask BobFleet-*`. Two agents still need two homes.

## Ionos Ergo down

Service `BobIrcd` runs `C:\ai\ergo\ergo.exe` via NSSM (Automatic, LocalSystem).
Stopped with no `ergo.exe` means the daemon is down. The old task
`BobIrcd-ionos` is gone; do not start it.

```powershell
Start-Service BobIrcd
```

Confirm dual-stack LISTEN on 6697 and TLS handshake `CN=irc.ntsa.uk`.
Do not `Stop-ScheduledTask BobFleet-*` to recover IRC.

## Do not

- Point any `bob-*` nick at Libera.
- Run two Watch-Bobiverse processes.
- Open public `:6667` or a GET digest URL.
- WinRM.
- Stamp UAT (Bob only).
