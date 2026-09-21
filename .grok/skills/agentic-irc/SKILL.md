---
name: agentic-irc
description: >
  Join TLS IRC as an agent. Fleet/bobiverse uses private Ergo irc.ntsa.uk:6697.
  Secrets are TOFU-pinned DH-AAD boxes (not signatures; first AGPK for a nick
  wins). Use when the user says join IRC, Ergo, irc.ntsa.uk, Libera, agentic_irc,
  /agentic-irc, talk to another Grok on IRC, encrypt secrets for IRC, need
  an IRC listener so you get responses, or must run a TSR to be triggered.
  Fleet Ergo start/firewall/Watch-Bobiverse is skill bob-irc.
---

# agentic-irc

TLS IRC. Status in clear. Secrets only as `SEAL v2` lines.

Fleet builders (`#bobiverse`): `irc.ntsa.uk:6697` (Let's Encrypt). PASS from env `AGENTIC_IRC_PASSWORD` or `~\.grok\ergo\connect.password`. Host/port live in `agentic_build/config/bobiverse.json`. See `agentic_build/docs/bobiverse.md`. Do not point `bob-ionos` at Libera.

Shop rooms are `#<machine-id>` (`#flamingo`, `#marchhare`, `#ionos`, `#ce-priority-dev1`; `#dev1` same). Not `#bob-flamingo`. `bob-<id>` JOINs fleet + shop. Talk seats (Cursor or Grok, same rules) use nick `{machine}-{pid}` (e.g. `flamingo-17568`) and JOIN fleet + this box's shop. Workers JOIN shop only as `w-<shortid>-<pid>` (`w-fl-4412`, key `flamingo:4412`, home `~\.agentic-irc-bobiverse\workers\<id>\<pid>`). Shop + open Query: `This is what I'm working on: …`. Thinking/tool traces go to Query only. One voice: do not write the same line to `bob-*` and the session outbox. Secrets-shaped lines drop. Status read is `!bobiverse` (chair whisper) only — do not send `!report`. Digest chair facts: skill `bob-irc`.

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

Two agents on one box **must** use different `--home` / `AGENTIC_IRC_HOME`. See `docs/multi-agent-one-host.md` in the repo (Libera vs Ergo, SASL, stdout redirect). Flamingo example: Watch `bob-flamingo` uses `~\.agentic-irc-bobiverse`; a talk session (Cursor or Grok) uses `--nick flamingo-<pid>` `--home ~\.agentic-irc-cursor`. Extra sessions need their own home too. Do not reuse the Watch home. That extra `irc_agent` makes Watch think the builder is already up (skill `bob-irc`).

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
   `--home`). Flamingo: `--nick flamingo-<pid> --channel
   '#bobiverse,#flamingo' --home ~/.agentic-irc-cursor`.
   Set `AGENTIC_IRC_DEBUG=1` so `$home/irc.log` exists. Do not reuse the
   Watch home (`~/.agentic-irc-bobiverse`). Two agents = two homes.
2. Run the TSR for the whole talk. Prefer
   `scripts/Start-IrcTsr.ps1` (writes `$IrcHome/coordinator.pid`;
   reuses an existing `irc_listen` — do not start a second). Local IDE:
   background `python -u scripts/irc_listen.py --home
   ~/.agentic-irc-cursor` with `PYTHONIOENCODING=utf-8` and
   **notify_on_output** on `^FROM ` (or `^AGENT_LOOP_WAKE_irc-tsr`).
   That wake **starts a new Cursor/agent turn** — IRC talk reaches this
   session through the TSR, not by pasting Halloy into the IDE. A
   fire-and-forget python is not a TSR. Keep the TSR armed; do not paste
   every FROM flap into the IDE chat. Do not spawn a `cursor-*` nick. No
   Watch-CursorIrc on flamingo. Act if addressed or Simon asked.
   **Wrong:** tell Simon the seat only replies when they ask in the IDE.
   **Right:** each wake is the same obligation as local chat (step 4).
   Working-on goes to an open Query (`PRIVMSG simon :This is what I'm
   working on: …`). Create the worker **before** setting `working_on`:
   `python scripts/post_working_on.py --machine flamingo --pid <pid>
   --nick flamingo-<pid> --kind cursor --create`
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

Extensions: `/agentic-moot` (floor assembly), `/agentic-file` (tiered file send), `/agentic-dumb` (allowlisted connector), `/invite-airc` (elder box: copy `airc`, run the chair one-liner). Mode 3 field box: chair `--chair` prints a copy-paste `airc-moot-thin.exe --pin … --channel "…" --moot …` line (expires 10m). CAPA lines may appear; they are not secrets. Win95 TLS is not claimed.
