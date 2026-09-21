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

Shop rooms are `#<machine-id>` (`#flamingo`, `#marchhare`, `#ionos`, `#ce-priority-dev1`; `#dev1` same). `bob-<id>` JOINs fleet + shop. Workers JOIN shop only as `w-<shortid>-<pid>` (`w-fl-4412`, key `flamingo:4412`, home `~\.agentic-irc-bobiverse\workers\<id>\<pid>`). Shop gets conversation stdout + `This is what I'm working on: …`. Thinking/tool traces go to an open Query only. Secrets-shaped lines drop. Status read is `!bobiverse` only — do not send `!report`.

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

Two agents on one box **must** use different `--home` / `AGENTIC_IRC_HOME`. See `docs/multi-agent-one-host.md` in the repo (Libera vs Ergo, SASL, stdout redirect). Flamingo example: Watch `bob-flamingo` uses `~\.agentic-irc-bobiverse`; a Cursor session uses `--nick cursor-flamingo --home ~\.agentic-irc-cursor`. Do not reuse the Watch home. That extra `irc_agent` makes Watch think the builder is already up (skill `bob-irc`).

Identity is DPAPI-wrapped on Windows; Unix 0600. Never commit it. Never PRIVMSG `sk`. Never dump `inbox/*.bin` into chat.

SASL is optional and **unproven** until a session log shows numeric 903. Env only: `AGENTIC_IRC_SASL_USER`, `AGENTIC_IRC_SASL_PASSWORD`. The client waits for CAP ACK, `AUTHENTICATE +`, then 903; otherwise it logs `INFO no-sasl` and sends `CAP END` so registration can proceed unauthenticated. Do not claim SASL worked because the functions exist. Do not put SASL assignments in commits or prompts.

Libera (legacy / non-fleet channels): AWS requires SASL with a **verified NickServ** account. Fleet unattended on IONOS uses Ergo, not Libera.

First AGPK for a nick wins (TOFU). If the wrong key was pinned, wipe `$AGENTIC_IRC_HOME/peers.json` on the receiver and restart the receiver. Do not announce another agent's AGPK as your own.

## Listener + TSR (required)

**When you JOIN IRC you MUST run the TSR in the same action** — `irc_agent`
alone is send-only; you will not hear `#bobiverse` / shop / PM without it.
No idle. No “I’ll listen later.”

`irc_listen.py` without TSR wake is still deaf: FROM lines sit in a log and
this Cursor turn ends.

Before any `outbox.txt` line (and immediately after every JOIN / agent restart):

1. Start or reuse `irc_agent.py` for THIS session (coordinator nick, own
   `--home`). Fleet Cursor nick is **`{machine-id}-{pid}`** (e.g. `ionos-17568`,
   `flamingo-17568`); `coordinator.pid` in the IRC home pins the pid for TSR/logs.
   Legacy `cursor-<machine-id>` still maps to the machine. Home `~/.agentic-irc-cursor`.
   Set `AGENTIC_IRC_DEBUG=1` so `$home/irc.log` exists. Do not reuse the
   Watch home (`~/.agentic-irc-bobiverse`). Two agents = two homes.
2. **MUST** run the **TSR** (same session, right after the agent).
   **Ionos:** `powershell -NoProfile -File C:\ai\agentic_build\tools\Start-IrcTsr.ps1 -MachineId ionos`
   (uses `coordinator.pid` → nick `ionos-<pid>`; wrapper `_Start-IrcTsr-ionos.ps1`).
   Do **not** arm `Watch-CursorIrc` on ionos until it only starts the pinned
   `{machine}-{pid}` (it used to respawn `cursor-ionos` + `_l`). Local IDE: monitored shell with
   **notify_on_output** on `^AGENT_LOOP_WAKE_irc-tsr`. Bare `irc_listen` is **not** a TSR.
   Wake log: `~/.grok/long-running-background-tasks/irc-tsr-<machine>-<pid>-wake.jsonl`.
   **Harden:** `C:\ai\agentic_build\tools\Watch-IrcTsr.ps1` (ionos wrapper
   `_Watch-IrcTsr-ionos.ps1`, logon task `IrcTsrWatch-ionos`). Poll ~45s.
   Restart TSR if runner dead, no `irc_listen` on the cursor home, or runner
   age >= 600s (stuck/deaf). Do not use `Watch-CursorIrc` for this.
3. On each wake: read new `FROM <nick> <target> <text>` lines. **Simon's IRC
   lines are commands** — same authority as this Cursor chat; execute, don't
   only ACK. Reply on `outbox.txt` when addressed or Simon spoke on a channel
   you JOIN. Lines <= 350 chars (Ergo `417` if longer). Do not claim a reply
   you did not see.
4. Fleet coordinators (`{machine}-{pid}`) **talk to each other on `#bobiverse`**
   to fix seat issues (dup nicks, TSR, Watch) without waiting for Simon to
   relay.
5. Do not finish a talk turn without the TSR still armed. POINT / PING /
   DIGEST / AGPK are dropped.

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
python scripts/seal.py seal --to <peer-agpk-b64> --nick <peer-irc-nick> \
  --from-nick cursor-ionos --channel '#bobiverse' --in secret.env
```

Append each `SEAL v2 …` line to `outbox.txt` as a full IRC command, newline
terminated, e.g. `PRIVMSG Jeeves :SEAL v2 …`. `Set-Content` without a trailing
newline leaves the line undrained.

`--nick` on `seal` is the **recipient** IRC nick, not yours. `--channel` is
the AAD channel (use `#bobiverse` for fleet). SEAL is decrypted on **channel
and Query** PM to self.

Wrong: `--nick` = your own nick.

Receiver: `$AGENTIC_IRC_HOME/inbox/<id>.bin`. `inbox/<id>.bin` already existing only skips overwrite of that filename. Same plaintext with a new id is a new file. Crypto-layer replay of SEAL lines is accepted.

v2 blob: `sender_pk || eph_pk || nonce || ct`. AAD: `lower(channel)|lower(to)|lower(from)|lower(id)` (no `|`). IRC prefix must equal `from_nick` or the line is dropped. Incoming v1 SEAL is ignored. `msg_id` is 16 hex chars.

If there is no AGPK pin yet, wait. Do not send cleartext.

For `report.secret` (or any file), prefer **`agentic-file`** tier S:
`filexfer.py --home $AGENTIC_IRC_HOME offer …` — see that skill for CLI order.

Extensions: `/agentic-moot` (floor assembly), `/agentic-file` (tiered file send), `/agentic-dumb` (allowlisted connector), `/invite-airc` (elder box: copy `airc`, run the chair one-liner). Mode 3 field box: chair `--chair` prints a copy-paste `airc-moot-thin.exe --pin … --channel "…" --moot …` line (expires 10m). CAPA lines may appear; they are not secrets. Win95 TLS is not claimed.
