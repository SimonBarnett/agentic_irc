---
name: agentic-irc
description: >
  Join Libera TLS IRC as an agent, keep a channel alive, and pass secrets as
  authenticated X25519 boxes (never plaintext). Use when the user says join IRC,
  Libera, agentic_irc, /agentic-irc, talk to another Grok on IRC, or encrypt
  secrets for IRC.
---

# agentic-irc

Libera `irc.libera.chat:6697` TLS. Status in clear. Secrets only as `SEAL v2` lines.

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

SASL is optional and **unproven** until a session log shows numeric 903. Env only: `AGENTIC_IRC_SASL_USER`, `AGENTIC_IRC_SASL_PASSWORD`. The client waits for CAP ACK, `AUTHENTICATE +`, then 903; otherwise it logs `INFO no-sasl` and continues unauthenticated. Do not claim SASL worked because the functions exist.

## Connect

```bash
python ~/.grok/skills/agentic-irc/scripts/irc_agent.py --nick grok-box-a --channel '#ops' --home ~/.agentic-irc-a --announce-key --hello 'box-a online'
```

Stdout is INFO only (`AGENTIC_IRC_DEBUG=1` writes `irc.log`).

433: `live_nick` becomes `original_nick_l` once; reconnect resets to `original_nick`. SEAL addressed to the **original** nick still decrypts. AAD uses the nick in the SEAL line (the one the peer pinned).

## Secrets

```bash
python ~/.grok/skills/agentic-irc/scripts/seal.py seal --to <peer-agpk-b64> --nick <peer-irc-nick> --from-nick grok-box-a --channel '#ops' --in secret.env >> $AGENTIC_IRC_HOME/outbox.txt
```

Wrong: `--nick` = your own nick.

Receiver: `$AGENTIC_IRC_HOME/inbox/<id>.bin`. `inbox/<id>.bin` already existing only skips overwrite of that filename. Same plaintext with a new id is a new file. Crypto-layer replay of SEAL lines is accepted.

v2 blob: `sender_pk || eph_pk || nonce || ct`. AAD: `channel|to_nick|from_nick|msg_id`. v1 parse only; do not send v1.

If there is no AGPK pin yet, wait. Do not send cleartext.
