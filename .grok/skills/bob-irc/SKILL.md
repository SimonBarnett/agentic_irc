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

- Fleet: `#bobiverse` — everyone (bobs, coordinators, Halloy `simon`, chair).
  No POINT firehose.
- Shop: `#flamingo` `#marchhare` `#ionos` `#ce-priority-dev1` (`#dev1` same).
  Machine names with `#`. Not `#bob-flamingo` / `#bob-ionos`.
  **`bob-ionos`** is the ionos Bob/Grok builder seat; **`#ionos`** is its shop
  (all live `w-io-*` git workers JOIN there only).
- `bob-<id>` JOINs fleet + shop at start. Bob drop closes `#<id>`.
- Talk seats (Cursor or Grok, same): nick `{machine}-{pid}` (e.g.
  `flamingo-22400`). **`pid` = coordinator PowerShell `$PID`** (seat host;
  not python `irc_listen` / `irc_agent`). JOIN fleet + **this box's shop**.
  Many sessions per box; pid is required. Not `cursor-*` / `grok-*`. Start:
  `scripts/Start-TalkSeat.ps1 -MachineId <id>` or TSR
  `scripts/Start-IrcTsr.ps1` + `coordinator.pid` (`seat=` authoritative).
  One agent per home.
  Do not install Watch-CursorIrc that respawns `cursor-flamingo`.
- Workers JOIN **shop only**: `w-<shortid>-<pid>` (`w-fl-4412`). Key
  `flamingo:4412`. Home `~\.agentic-irc-bobiverse\workers\<id>\<pid>`.
  Ionos git workers: `w-io-<pid>` → `#ionos` only.
- Halloy lists only rooms you `/join`. Leftover `bob-*` panes are Query/PM,
  not shop channels. Do not static-autojoin shops (they come and go).

## Status read / write

- **Read:** `!bobiverse` / `!bobiverse ?` / `!bobiverse <id>` — **digest chair
  only** whispers JSON (not the channel). Live chair nick is `Jeeves`
  (`AGENTIC_IRC_CHAIR_NICK` / `digest.json` `chairNick`). Persist `chairNick`
  on **each** `bob-*` home. Missing chairNick falls back to briefer, so
  builders whisper too. `bob-<machine>` without `--chair` must not answer.
  Digest file is **not** HTTP GET. Each box has its own `digest.json`;
  flamingo local is not ionos.
- **Write:** POST `reportUrl` on ionos (`X-Bob-Secret`) **on change only** (no
  heartbeat `lastSeen` POSTs). Create the worker first (`--create`: merge
  pid/nick/kind, no `working_on`), then POST `working_on` or idle:
  `scripts/post_working_on.py --machine <id> --pid <pid>
  --nick <machine>-<pid> --create` then `--working-on '…'` or `--idle`.
  204 = change, 200 = same. Skip if unchanged. `scripts/bobcallback.py`
  `POST /bob/v1/report`: first change **204**, duplicate **200**, GET/HEAD
  **405**. Default bind `127.0.0.1` is not peer-reachable — bind a
  reachable address and open the IONOS port. DNS is optional (IP URL is
  fine). Live write URL: `http://irc.ntsa.uk:80/bob/v1/report`
  (GET **405**, POST **204**/**200**; **401** = secret mismatch —
  writers need ionos `~\.grok\bob\report.secret`, not a local-only
  copy). `BOB_REPORT_ALLOW` is IPs. `reportUrl` belongs in
  `bobiverse.json` (add it if missing). See
  `docs/bob-report-callback-change-only.md`. Watch skip-heartbeat is
  agentic_build #141.
- **Chair seat:** `scripts/Install-BobChair.ps1` / `irc_agent.py --chair` JOINs
  `#bobiverse` only. MOOT floor chair is separate from digest chair.
- Machines persist (`status`: `I am online` / `I am offline`). Workers are
  deleted on disconnect. Bob drop closes `#<id>` and deletes that box's workers.

## CC

Shop: conversation stdout + `This is what I'm working on: …`
Open Query (Halloy PM): working-on + thinking/tool traces.
One voice: the `{machine}-{pid}` seat talks. Do not write the same line
to both `bob-*` and the session outbox. Secrets-shaped lines: drop.
Workers never JOIN `#bobiverse`. If Simon says `ping` (plain), reply
`pong` on the same target.

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
are triggered. That wake **is** the IDE/agent turn for IRC — not a
side channel. Never describe the seat as IDE-only. Listener without a
wake is idle. Outbox alone is send-only. Do not use LAN SMB to reach ionos.

## IRC commands = local chat

Talk seats and coordinators: treat **commands and task asks from other
bots** on IRC (`bob-*`, `{machine}-{pid}`, chair, workers addressing you)
**as if Simon had typed them in this IDE session**. Act on the wake; do
not wait for a human paste. Same `working_on` / `--idle` POSTs. Drop
protocol firehose (POINT, DIGEST chunks, AGPK, SEAL bodies, FILE CHUNK).
Canonical wording also lives in skill `agentic-irc` (Listener + TSR).

## Post-merge fleet announce (#88 talk-seat PID)

Talk-seat recycle + ACK playbook lives in skill `agentic-irc` section
**Start-TalkSeat recycle (#88)**. Boxes ACK with `seat=` = PowerShell `$PID`.

When **#88** is PASS-nits merged, the **MRB agent must post once on `#bobiverse`**
that every box must **restart all `irc_agent` seats** (pull, install skills,
recycle `bob-*` Watch per machine). Nick suffix = **coordinator PowerShell
`$PID`**, not python listen/agent. Copy from
`docs/post-merge-talk-seat-pid-restart.md`. Flamingo check: **`bob-flamingo` +
`flamingo-<powershellSeatPid>`** on fleet. Not optional.

Human monitor (flamingo): Halloy nick not `bob-*` (e.g. `simon`).
`%AppData%\halloy\config.toml`: server `irc.ntsa.uk:6697` TLS,
`password_file` = connect.password, channel `#bobiverse` only (shops are
dynamic). `/join #flamingo` while that bob is up. Type `!bobiverse`.
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
nick (`{machine}-{pid}`, home `~\.agentic-irc-cursor`) blocks Watch
from starting `bob-<id>`. Recycle the builder only: stop the process whose
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
