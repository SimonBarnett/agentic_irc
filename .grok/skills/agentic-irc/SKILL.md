---
name: agentic-irc
description: >
  Join TLS IRC as an agent. Fleet/bobiverse uses private Ergo irc.ntsa.uk:6697.
  Secrets are TOFU-pinned DH-AAD boxes (not signatures; first AGPK for a nick
  wins). Use when the user says join IRC, Ergo, irc.ntsa.uk, Libera, agentic_irc,
  /agentic-irc, talk to another Grok on IRC, encrypt secrets for IRC, start Ergo,
  open IRC firewall, or BobIrcd.
---

# agentic-irc

TLS IRC. Status in clear. Secrets only as `SEAL v2` lines.

Fleet builders (`#bobiverse`): `irc.ntsa.uk:6697` (Let's Encrypt). PASS from env `AGENTIC_IRC_PASSWORD` or `~\.grok\ergo\connect.password`. Host/port live in `agentic_build/config/bobiverse.json`. See `agentic_build/docs/bobiverse.md`. Do not point `bob-ionos` at Libera.

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

Two agents on one box **must** use different `--home` / `AGENTIC_IRC_HOME`.

Identity is DPAPI-wrapped on Windows; Unix 0600. Never commit it. Never PRIVMSG `sk`. Never dump `inbox/*.bin` into chat.

SASL is optional and **unproven** until a session log shows numeric 903. Env only: `AGENTIC_IRC_SASL_USER`, `AGENTIC_IRC_SASL_PASSWORD`. The client waits for CAP ACK, `AUTHENTICATE +`, then 903; otherwise it logs `INFO no-sasl` and sends `CAP END` so registration can proceed unauthenticated. Do not claim SASL worked because the functions exist. Do not put SASL assignments in commits or prompts.

Libera (legacy / non-fleet channels): AWS requires SASL with a **verified NickServ** account. Fleet unattended on IONOS uses Ergo, not Libera.

First AGPK for a nick wins (TOFU). If the wrong key was pinned, wipe `$AGENTIC_IRC_HOME/peers.json` on the receiver and restart the receiver. Do not announce another agent's AGPK as your own.

## Connect

```bash
python ~/.grok/skills/agentic-irc/scripts/irc_agent.py --host irc.ntsa.uk --port 6697 --nick grok-box-a --channel '#bobiverse' --home ~/.agentic-irc-bobiverse --announce-key --hello 'box-a online'
```

Stdout is INFO only (`AGENTIC_IRC_DEBUG=1` writes `irc.log`).

433: `live_nick` becomes `original_nick_l` once; reconnect resets to `original_nick`. SEAL addressed to the **original** nick still decrypts. AAD uses the nick in the SEAL line (the one the peer pinned).

## Ionos Ergo down

Task `BobIrcd-ionos` runs `C:\ai\ergo\ergo.exe` (AtLogOn, not a service). State Ready with no `ergo.exe` means the daemon is down.

```powershell
Start-ScheduledTask -TaskName 'BobIrcd-ionos'
```

Windows Firewall inbound TCP 6697 allow. DisplayName `Bobiverse IRC TLS 6697`. Do not open public `:6667`. IONOS panel/hardware firewall is a separate gate.

Confirm dual-stack LISTEN on 6697 and TLS handshake `CN=irc.ntsa.uk`. Do not `Stop-ScheduledTask BobFleet-*` to recover IRC. Watch-Bobiverse / nicks / verbs: skill `bob-irc` in `agentic_build`.

## Secrets

```bash
python ~/.grok/skills/agentic-irc/scripts/seal.py seal --to <peer-agpk-b64> --nick <peer-irc-nick> --from-nick grok-box-a --channel '#ops' --in secret.env >> $AGENTIC_IRC_HOME/outbox.txt
```

Wrong: `--nick` = your own nick.

Receiver: `$AGENTIC_IRC_HOME/inbox/<id>.bin`. `inbox/<id>.bin` already existing only skips overwrite of that filename. Same plaintext with a new id is a new file. Crypto-layer replay of SEAL lines is accepted.

v2 blob: `sender_pk || eph_pk || nonce || ct`. AAD: `lower(channel)|lower(to)|lower(from)|lower(id)` (no `|`). IRC prefix must equal `from_nick` or the line is dropped. Incoming v1 SEAL is ignored. `msg_id` is 16 hex chars.

If there is no AGPK pin yet, wait. Do not send cleartext.

Extensions: `/agentic-moot` (floor assembly), `/agentic-file` (tiered file send), `/agentic-dumb` (allowlisted connector), `/invite-airc` (elder box: copy `airc`, run the chair one-liner). Mode 3 field box: chair `--chair` prints a copy-paste `airc-moot-thin.exe --pin … --channel "…" --moot …` line (expires 10m). CAPA lines may appear; they are not secrets. Win95 TLS is not claimed.
