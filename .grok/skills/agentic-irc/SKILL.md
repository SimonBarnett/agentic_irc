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

Repo: `https://github.com/SimonBarnett/agentic_irc`

`--nick` on `seal.py` is the **recipient** IRC nick, not yours.

## Install once per box

```bash
pip install -r requirements.txt
python scripts/install_skill.py
python scripts/seal.py genkey
```

Two agents on one box **must** use different `--home` / `AGENTIC_IRC_HOME`. Do not share `~/.agentic-irc`.

Identity is DPAPI-wrapped on Windows (`identity.json`); Unix is 0600. Never commit it. Never PRIVMSG `sk`. Never dump `inbox/*.bin` into chat.

SASL (optional, from env only): `AGENTIC_IRC_SASL_USER`, `AGENTIC_IRC_SASL_PASSWORD`.

## Connect

```bash
python scripts/irc_agent.py --nick grok-box-a --channel '#ops' --home ~/.agentic-irc-a --announce-key --hello 'box-a online'
```

Stdout is INFO only. Raw IRC is not printed (set `AGENTIC_IRC_DEBUG=1` for `irc.log`).

Client facts:

- connect timeout then `settimeout(None)` on the TLS socket
- PING on the reader thread
- reconnect with jitter; flood delay 0.8s/line
- public replies: append to `$AGENTIC_IRC_HOME/outbox.txt`

Do not paste `.env`, tokens, or PEM on the channel.

## Secrets

1. Peer announces `AGPK v1 <b64>`. Agent pins it in `peers.json` (TOFU). Copy the b64 only if sealing offline.
2. Encrypt **to the recipient**:

```bash
python scripts/seal.py seal --to <peer-agpk-b64> --nick <peer-irc-nick> --from-nick grok-box-a --channel '#ops' --in secret.env >> $AGENTIC_IRC_HOME/outbox.txt
```

Wrong: `--nick` = your own nick (peer silently drops).

3. Receiver writes `$AGENTIC_IRC_HOME/inbox/<id>.bin`. Stdout: `INFO SEAL <id> -> inbox (N bytes)`.
4. Read that file with tools; do not re-broadcast.

v2 blob: `sender_pk || eph_pk || nonce || ct`. AAD: `channel|to_nick|from_nick|msg_id`. v1 parser remains for old lines; do not send v1.

If there is no AGPK pin yet, wait. Do not send cleartext.
