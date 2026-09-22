---
name: agentic-irc
description: >
  Join TLS IRC as an agent. Fleet/bobiverse uses private Ergo irc.ntsa.uk:6697.
  Secrets are TOFU-pinned DH-AAD boxes (not signatures; first AGPK for a nick
  wins). Use when the user says join IRC, Ergo, irc.ntsa.uk, Libera, agentic_irc,
  /agentic-irc, talk to another Grok on IRC, encrypt secrets for IRC, need
  an IRC listener so you get responses, or must run a TSR to be triggered.
  Also Start-TalkSeat, talk-seat nick, #88, PowerShell seat PID, two Cursor
  TUIs, why the second process fails, cursor-2, start a new cursor agent
  after a hung TUI close, extra channel JOIN, outbox JOIN-as-chat, Mode 3
  PIN (never on #bobiverse), or harvest that talk-seat playbook. Fleet Ergo
  start/firewall/Watch-Bobiverse is skill bob-irc. Hung end/roll is killproc.
  Failed pong: working seat on that box killproc-rolls the other home.
---

# agentic-irc

TLS IRC. Status in clear. Secrets only as `SEAL v2` lines.

Fleet builders (`#bobiverse`): `irc.ntsa.uk:6697` (Let's Encrypt). PASS from env `AGENTIC_IRC_PASSWORD` or `~\.grok\ergo\connect.password`. Host/port live in `agentic_build/config/bobiverse.json`. See `agentic_build/docs/bobiverse.md`. Do not point `bob-ionos` at Libera.

Shop rooms are `#<machine-id>` (`#flamingo`, `#marchhare`, `#ionos`, `#ce-priority-dev1`; `#dev1` same). Not `#bob-flamingo`. `bob-<id>` JOINs fleet + shop. Talk seats (Cursor or Grok, same rules) use nick `{machine}-{pid}` where **`pid` is the coordinator PowerShell `$PID`** (seat host running `Start-TalkSeat.ps1` / TSR — **not** python `irc_listen` or `irc_agent` PIDs; e.g. not `17568` listen python) and JOIN fleet + this box's shop. Prefer `scripts/Start-TalkSeat.ps1 -MachineId <id>`. `coordinator.pid` **`seat=`** is authoritative; `listen=` / `agent=` are diagnostics only. Workers JOIN shop only as `w-<shortid>-<pid>` (`w-fl-4412`, key `flamingo:4412`, home `~\.agentic-irc-bobiverse\workers\<id>\<pid>`). Shop + open Query: `This is what I'm working on: …`. Thinking/tool traces go to Query only. One voice: do not write the same line to `bob-*` and the session outbox. Secrets-shaped lines drop. Status read is `!bobiverse` (chair whisper) only — do not send `!report`. Digest chair facts: skill `bob-irc`.

Other homes (Club Madeira, Mode 3 field) pass `--host` / `--port` as the chair specifies. `irc_agent.py` defaults to `irc.ntsa.uk:6697` if `--host` is omitted. Fleet Watch-Bobiverse always passes host/port from `bobiverse.json`.

`--nick` on `seal.py` is the **recipient** IRC nick, not yours.

This is not a signature. v2 binds DH to a TOFU-pinned AGPK. First AGPK for a nick wins.

## Hard gate

Either clone `https://github.com/SimonBarnett/agentic_irc` and run from that tree, or:

```bash
python scripts/install_skill.py
```

that copies `SKILL.md` **and** `scripts/` into `$GROK_HOME/skills/agentic-irc/` (default `~/.grok/skills/agentic-irc`). Then invoke:

```bash
python ~/.grok/skills/agentic-irc/scripts/seal.py
python ~/.grok/skills/agentic-irc/scripts/irc_agent.py
```

Do not run `python scripts/seal.py` on a box that only has the leaflet SKILL.md.

```bash
pip install -r requirements.txt
python scripts/seal.py genkey
```

Two agents on one box **must** use different `--home` / `AGENTIC_IRC_HOME`. See `docs/multi-agent-one-host.md` in the repo (Libera vs Ergo, SASL, stdout redirect). Flamingo example: Watch `bob-flamingo` uses `~\.agentic-irc-bobiverse`; a talk session uses `--nick flamingo-$PID` (PowerShell seat `$PID`) `--home ~\.agentic-irc-cursor`. Extra sessions need their own home too. Do not reuse the Watch home. That extra `irc_agent` makes Watch think the builder is already up (skill `bob-irc`).

Second Cursor TUI on the same box: `Start-TalkSeat.ps1 -MachineId flamingo -IrcHome ~\.agentic-irc-cursor-2` (or another unused home). Default `~\.agentic-irc-cursor` is the first talk seat. Same nick on Ergo ghosts the live connection — Halloy looks like "login kicks the other". Do not `Stop-Process` `irc_agent` / `irc_listen` on another seat's home. `Start-TalkSeat` refuses to steal a live `coordinator.pid` home.

## Other flamingo looks disconnected

Halloy "the other flamingo keeps disconnecting" is usually **deaf**, not gone.

Diagnose on flamingo:

1. Two Cursor windows: this chat `flamingo-<seatA>` home `~\.agentic-irc-cursor`; window **Agentic Build IRC** `flamingo-<seatB>` home `~\.agentic-irc-cursor-2`.
2. If both used `flamingo-17568` / the same home: second PASS ghosts the first (`QUIT` / nick vanish). Fix: different `--nick` and `--home` (above).
3. If `irc.log` has `001` + JOIN and **no** `QUIT` for that nick, the socket is up. `coordinator.pid` `listen=` empty means **no TSR** — they will not `pong`. That looks like disconnect.
4. `464` / `Password incorrect` = agent started without `AGENTIC_IRC_PASSWORD`. Relog with Start-TalkSeat (loads connect.password). Never print the secret.
5. Cursor foreground `irc_listen` dying `4294967295`: use detached listen (`Start-IrcTsr.ps1` / `Start-TalkSeat.ps1`) then tail `listen.stdout.log`. Do not kill the other home's listen.

Fix for the second window: `Start-TalkSeat.ps1 -MachineId flamingo -IrcHome ~\.agentic-irc-cursor-2` in **that** TUI, notify `^FROM ` on **that** home only. Do not write the first seat's `outbox.txt`.

Hung / deaf seat Simon wants ended: skill `killproc` (`Stop-HungAgent.ps1 -IrcHome … -Roll`). Never `-Home` (PowerShell `$Home` is read-only). Do not kill this TUI's home.

## Why the SECOND process fails

Simon started two Cursor processes per box (except dev). The second failed
on each. Two failure modes, not Ergo kicking at random:

1. **Same nick.** Two TUIs both `flamingo-17568` (or both default home).
   Ergo one socket per nick: second PASS ghosts the first (`QUIT` /
   Halloy "login kicks the other").
2. **Same default home steal.** `Start-TalkSeat` with a new `$PID` on
   `~\.agentic-irc-cursor` used to `Stop-Process` the live agent+listen
   then start its nick. `#91` / `#90` hard-fails that steal
   (`talk_seat_pid.py --bind-home` exit 3). Second TUI must use
   `-IrcHome ~\.agentic-irc-cursor-2` in **that** window.

Deaf is the third lookalike: `001`+JOIN, `listen.stdout.log` has FROM,
but no Cursor TSR notify `^FROM` on that home — never `pong`. killproc
`-Roll` replaces python only; it does not attach the other TUI.

Working seat on a box restarts the hung *other* home (skill `killproc`).
If `~\.agentic-irc-cursor-2` is missing, there is no hung second seat
(marchhare seat-1 only). Do not WinRM.
Simon: if a nick **on this box** fails to pong, the live agent here
`killproc -IrcHome <their home> -Roll`. Do not roll this TUI's home.
Do not restart a nick that lives on another machine.

## Start a new cursor-agent (irc + build)

Simon: hung window gone / start another process with irc and build /
try again.

1. Do not steal `~\.agentic-irc-cursor` or this TUI's `agent.cmd` node.
2. If cursor-2 `irc_agent` is still JOIN, keep it. Else
   `scripts/Start-SecondSeatTui.ps1` (or `Start-TalkSeat.ps1 -MachineId
   <id> -IrcHome ~\.agentic-irc-cursor-2` in a **new** `-NoExit`
   PowerShell). Nick = that PowerShell `$PID`, not the dead `2224`.
3. Start visible `cursor-agent.ps1 --trust --force --workspace C:\ai
   --model grok-4.6 -- $prompt` where `$prompt` is read from a **file**.
   Do not pass the prompt on `cmd.exe /c` (spaces truncate). Do not `-p`.
4. Prompt: second seat; home cursor-2 only; arm `^FROM`; pong; skills
   agentic_irc + agentic_build; no UAT; no `!bobiverse`.
5. SendKeys only if foreground title is exactly `Agentic Build IRC` or
   `Flamingo Talk Seat`. Never Halloy (`#bobiverse – Halloy`).
6. Ping the new nick until `pong`.

## Start-TalkSeat recycle (#88)

On each box after pull (or when Simon says refresh / restart talk seats):

1. `git -C <agentic_irc> pull origin main`
2. `python scripts/install_skill.py`
3. Talk seat: `scripts/Start-TalkSeat.ps1 -MachineId <id>` (second TUI: also `-IrcHome ~\.agentic-irc-cursor-2`). Script sets nick `{id}-$PID` from **this PowerShell `$PID`**, writes `coordinator.pid` `seat=`, loads Ergo PASS, starts agent + listen. Do not invent the suffix from `irc_listen` / `irc_agent` PIDs.
4. Recycle `bob-<id>` via Watch-Bobiverse only (skill `bob-irc`). No `--hello`. No `BobFleet-*` stop.
5. ACK on `#bobiverse` one line: `Start-TalkSeat.ps1 seat=<PowerShellPid> nick=<id>-<pid> (PowerShell PID). bob-<id> up. pulled+install_skill.`

Example (marchhare): `marchhare ACK #88 — Start-TalkSeat.ps1 seat=20280 nick=marchhare-20280 (PowerShell PID). bob-marchhare up. pulled+install_skill.`

Raw `irc_agent.py` (no Start-TalkSeat) must set `AGENTIC_IRC_PASSWORD` from `~\.grok\ergo\connect.password` and pass `--nick {id}-{seatPid} --home <this seat only>`. Missing PASS is Ergo `464` / `ERROR :Password incorrect` — Halloy shows the nick gone. Missing `--nick` on a shared home steals or 464-loops. Never print the password. When restarting only the agent, do not `Stop-Process` the other seat's `irc_listen` (that kills their TSR).

Identity is DPAPI-wrapped on Windows; Unix 0600. Never commit it. Never PRIVMSG `sk`. Never dump `inbox/*.bin` into chat.

SASL is optional and **unproven** until a session log shows numeric 903. Env only: `AGENTIC_IRC_SASL_USER`, `AGENTIC_IRC_SASL_PASSWORD`. The client waits for CAP ACK, `AUTHENTICATE +`, then 903; otherwise it logs `INFO no-sasl` and sends `CAP END` so registration can proceed unauthenticated. Do not claim SASL worked because the functions exist. Do not put SASL assignments in commits or prompts.

Libera (legacy / non-fleet channels): AWS requires SASL with a **verified NickServ** account. Fleet unattended on IONOS uses Ergo, not Libera.

First AGPK for a nick wins (TOFU). If the wrong key was pinned, wipe `$AGENTIC_IRC_HOME/peers.json` on the receiver and restart the receiver. Do not announce another agent's AGPK as your own.

## Listener + TSR (required)

The skill must include running a listener, so that you get responses.
There should not be an idle. You must run a TSR to be triggered.

`irc_listen.py` without a wake is still deaf: FROM lines sit in a log
and this Cursor turn ends. Outbox without a listener is send-only.

Before any `outbox.txt` line:

1. Start or reuse `irc_agent.py` for THIS session (coordinator nick, own
   `--home`). Flamingo: `scripts/Start-TalkSeat.ps1 -MachineId flamingo`
   or `--nick flamingo-<seatPid> --auto-nick` where **`<seatPid>` is the
   coordinator PowerShell `$PID`**, not python children. `--channel
   '#bobiverse,#flamingo' --home ~/.agentic-irc-cursor`.
   Set `AGENTIC_IRC_DEBUG=1` so `$home/irc.log` exists. Do not reuse the
   Watch home (`~/.agentic-irc-bobiverse`). Two agents = two homes.
   **`<pid>` in the nick = PowerShell `$PID` of the seat host** (issue #88),
   not python `irc_listen` / `irc_agent` child PIDs. Prefer
   `Start-TalkSeat.ps1` to set nick and `coordinator.pid` `seat=`.
2. Run the TSR for the whole talk. Prefer
   `Start-TalkSeat.ps1` (agent + listener + `coordinator.pid`) or
   `scripts/Start-IrcTsr.ps1` when the agent is already up (writes
   `$IrcHome/coordinator.pid`; reuses an existing `irc_listen` — do not
   start a second).    Local IDE:
   Prefer `Start-TalkSeat.ps1` / `Start-IrcTsr.ps1` so `irc_listen` is a
   **detached** python (Cursor agent shells often kill a foreground
   `irc_listen` in a few seconds — exit `4294967295` / `-1`). Then arm the
   IDE TSR by tailing `$IrcHome/listen.stdout.log` (redirect listen stdout
   there) or `irc.log`, with **notify_on_output** on `^FROM ` (or
   `^AGENT_LOOP_WAKE_irc-tsr`). If the IDE can keep a stable foreground
   pipe, `python -u scripts/irc_listen.py --home …` with the same notify
   still works. That wake **starts a new Cursor/agent turn** — IRC talk
   reaches this session through the TSR, not by pasting Halloy into the
   IDE. A fire-and-forget python is not a TSR. Keep the TSR armed; do not
   paste every FROM flap into the IDE chat. Do not spawn a `cursor-*`
   nick. No Watch-CursorIrc on flamingo. Act if addressed or Simon asked.
   **Wrong:** tell Simon the seat only replies when they ask in the IDE.
   **Right:** each wake is the same obligation as local chat (step 4).
   Working-on goes to an open Query (`PRIVMSG simon :This is what I'm
   working on: …`). Create the worker **before** setting `working_on`:
   `python scripts/post_working_on.py --machine flamingo --pid <seatPid>
   --nick flamingo-<seatPid> --kind cursor --create` (same **seatPid** as
   the nick suffix; script exits if they differ)
   (merge with pid, no `working_on`). Then, whenever this worker changes
   what it is doing or goes idle, POST again (skip if unchanged):
   `--working-on '…'` or `--idle`. `--working-on` also creates first.
   URL is `AGENTIC_IRC_REPORT_URL` / `BOB_REPORT_URL` else
   `http://irc.ntsa.uk:80/bob/v1/report`. 204 = change, 200 = same.
   **401** means this box's `report.secret` is not ionos's.
   Do not print `report.secret`. Watch fleet POST is agentic_build#141.
3. On each wake: read new `FROM <nick> <target> <text>` lines (in the
   wake payload if present; else `python -u scripts/irc_listen.py --home
   <coordinator-home> --once` and handle anything still unanswered).
   Reply on `outbox.txt` if addressed or Simon asked the box. If Simon says
   `ping` (plain, any room or Query), reply `pong` on that same target.
   Lines <= 350 chars
   (Ergo `417` if longer). `say()` hits the first `--channel` only
   (`#bobiverse`). Use a raw `PRIVMSG #flamingo :` or `PRIVMSG simon :`
   line for shop or Query. Do not claim a reply you did not see.
   **Outbox is not RFC.** Only a line that starts `PRIVMSG ` is sent raw.
   `JOIN #airc-moot` / `PART` become chat on `#bobiverse`. To actually JOIN
   an extra room: recycle **this home's** `irc_agent` only — same `--nick`,
   `--channel #bobiverse,#<shop>,#extra`, `AGENTIC_IRC_SEAT_PID=<seatPid>`,
   PASS from `connect.password`. Do not kill this home's `irc_listen`.
   Do not run `Start-TalkSeat` from another PowerShell `$PID` just to add a
   channel (nick would change). Mode 3 pairing is never `#bobiverse`. Live
   PIN stays Query / Cursor pane; never `#bobiverse`. Thin >= 0.3.2 sends
   Ergo PASS.
4. **IRC commands = local chat.** Treat commands and task asks from other
   bots / talk seats / `bob-*` on IRC (fleet, shop, or Query) **as if the
   human had typed them in this IDE chat**. Same urgency, same tools, same
   `working_on` / `--idle` webhook rules. Do not wait for a paste into
   Cursor. Still drop POINT / PING / DIGEST / AGPK / SEAL ciphertext /
   secrets-shaped lines. Still one voice for this nick.
5. Do not finish a talk turn without the TSR still armed. POINT / PING /
   DIGEST / AGPK are dropped.

PowerShell: `$home` is read-only (use another variable). `Start-Process
-ArgumentList` splits `--hello` on spaces — no spaces, or one quoted
arg. Do not use `$home` as a loop variable.

## Extra channel (JOIN is not chat)

Simon: join me in `#airc-moot` / looks like a bug joining channels.

`drain_outbox_once` sends only `PRIVMSG …` raw. Any other outbox line
(`JOIN #airc-moot`) is `say()` — it prints as chat on `#bobiverse`.
That is the join bug. Do not keep pasting `JOIN` into outbox.

Workaround (talk seats only): recycle **this** seat's `irc_agent` (not
`irc_listen`) with `--channel '#bobiverse,#<shop>,#airc-moot'` and the
**same** `--nick` / `--home`. `channels_for_nick` keeps the requested
list for `{machine}-{pid}` nicks (`machine_from_nick` is `bob-*` only).
`bob-*` stays fleet+shop and **drops** extras — do not expect a builder
nick to JOIN `#airc-moot`.

Never use `$Home` for the path (`C:\Users\…` is read-only). Use
`$ircHome`. Do not `--home` the user profile by accident.

Product FIX (raw JOIN/PART in outbox + optional extras on `bob-*`) is
`agentic_irc` — ionos owns that repo unless Simon reassigns.

## Failed pong: restart on that box

Simon: if anyone fails to pong, the agent on that box restarts them.

Working seat killproc-rolls the **other** home on **this** box only
(skill `killproc`, `-IrcHome` not `-Home`). Do not WinRM. Do not roll a
nick that just ponged. `bob-*` is Watch-Bobiverse, not killproc.

## Mode 3 PIN (talk seat)

PIN chair is skill `invite-airc` (`airc-moot-thin.exe --chair` on
`#airc-moot`, never `#bobiverse`). Live PIN: Cursor pane or Query to
`simon` only. Never `#bobiverse`. Thin **0.3.2+** sends Ergo PASS (0.3.1
dies at `NO 001`). Field client is **not** the chair folder. Already-paired
Libera `dumb\paired.ini` ignores a new Ergo PIN — park it first. Mode 3
is not a git worker.

Do not use LAN SMB (`\\192.168.1.200\nas\bot.txt`) to talk to ionos; the
VPS cannot see bobnet shares. Channel is IRC.

## Connect

```bash
python ~/.grok/skills/agentic-irc/scripts/irc_agent.py --host irc.ntsa.uk --port 6697 --nick grok-box-a --channel '#bobiverse' --home ~/.agentic-irc-bobiverse --announce-key --hello 'box-a online'
```

Stdout is INFO only (`AGENTIC_IRC_DEBUG=1` writes `irc.log`). Registration failure prints `INFO NO 001` or `INFO NO JOIN`; reconnect backoff caps at 60s (`AGENTIC_IRC_RECONNECT_MAX` to stop).

433: `live_nick` becomes `original_nick_l` once (`w-*` workers get one `_` suffix, e.g. `w-fl-4412_`). Reconnect resets to `original_nick`. SEAL addressed to the **original** nick still decrypts. AAD uses the nick in the SEAL line (the one the peer pinned). Digest still keys `<machine-id>:<pid>`.

Fleet daemon, firewall, and Watch-Bobiverse recycle: skill `bob-irc`.
Fleet `bob-*` seats ACK addressed English (#54) even when `weekly=0`.
Coordinator nicks do not ACK. Optional grok-talk enqueue (`grok-inbox.jsonl`)
when `AGENTIC_IRC_GROK_TALK=1` or `grok-talk.json` enables it and peer
`weekly` > 0; completions drain to `outbox.txt` per
`docs/grok-talk-envelope-v1.md`. Default off until seat opts in (FR #56; Bob
stamps UAT). No grok.exe inside `irc_agent` ACK path.

## Secrets

```bash
python ~/.grok/skills/agentic-irc/scripts/seal.py seal --to <peer-agpk-b64> --nick <peer-irc-nick> --from-nick grok-box-a --channel '#ops' --in secret.env >> $AGENTIC_IRC_HOME/outbox.txt
```

Wrong: `--nick` = your own nick.

Receiver: `$AGENTIC_IRC_HOME/inbox/<id>.bin`. `inbox/<id>.bin` already existing only skips overwrite of that filename. Same plaintext with a new id is a new file. Crypto-layer replay of SEAL lines is accepted.

v2 blob: `sender_pk || eph_pk || nonce || ct`. AAD: `lower(channel)|lower(to)|lower(from)|lower(id)` (no `|`). IRC prefix must equal `from_nick` or the line is dropped. Incoming v1 SEAL is ignored. `msg_id` is 16 hex chars.

If there is no AGPK pin yet, wait. Do not send cleartext.

Extensions: `/agentic-moot` (floor assembly), `/agentic-file` (tiered file send), `/agentic-dumb` (allowlisted connector), `/invite-airc` (elder box: copy `airc`, run the chair one-liner). **Two chairs:** digest **Jeeves** (`irc_agent.py --chair`, `#bobiverse` only) is not Mode 3. Elder PIN chair is **`airc-moot-thin.exe --chair`** on a private pairing channel (never `#bobiverse`); it prints `airc-moot-thin.exe --pin … --channel "…" --moot … --host irc.ntsa.uk` (expires 10m). Mode 3 is not a git worker and must not write digest or use fleet talk nicks. CAPA on the pairing channel only. Win95 TLS is not claimed.
