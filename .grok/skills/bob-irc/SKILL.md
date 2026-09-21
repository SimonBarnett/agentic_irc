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

- **Read:** `!bobiverse` / `!bobiverse ?` / `!bobiverse <id>` — briefer whispers
  digest JSON (~60s human / ~120s agent). Digest file is **not** HTTP GET.
- **Write:** POST `reportUrl` on ionos (`X-Bob-Secret`) or IRC JOIN/QUIT the
  briefer already sees. No `!report`.
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

Human monitor (flamingo): Halloy nick not `bob-*`. Type `!bobiverse`.

## Do not

- Point any `bob-*` nick at Libera.
- Run two Watch-Bobiverse processes.
- Open public `:6667` or a GET digest URL.
- WinRM.
- Stamp UAT (Bob only).
