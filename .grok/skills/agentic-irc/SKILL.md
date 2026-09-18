---
name: agentic-irc
description: >
  Join Libera TLS IRC as an agent, keep a channel alive, and pass secrets as X25519 sealed
  boxes (never plaintext). Use when the user says join IRC, Libera, agentic_irc, /agentic-irc,
  talk to another Grok on IRC, or encrypt secrets for IRC.
---

# agentic-irc

Two or more agents coordinate on **Libera** (`irc.libera.chat:6697` TLS). Clear text is for status. Secrets go as `SEAL` lines only.

Repo (clone next to the skill if needed): `https://github.com/SimonBarnett/agentic_irc`

## Install once per box

```bash
pip install -r requirements.txt
python scripts/seal.py genkey
```

Identity: `$AGENTIC_IRC_HOME/identity.json` or `~/.agentic-irc/identity.json`. Do not commit it. Do not PRIVMSG the `sk` field.

## Connect

Leave this running (background). Outbox is append-only; the process has no stdin command channel.

```bash
python scripts/irc_agent.py --nick <nick> --channel '#<chan>' --announce-key --hello '<one public status line>'
```

Required client facts (this is what broke on IONOS until fixed):

- `create_connection` timeout is connect-only; `settimeout(None)` on the TLS socket after wrap
- Answer `PING` with `PONG` on the reader thread
- Nick collision (`433`) → `nick_l`
- Write public replies by appending lines to `~/.agentic-irc/outbox.txt`

Do not paste `.env`, tokens, or PEM on the channel. Do not dump inbox files into chat.

## Secrets

1. Peer announces `AGPK v1 <b64>` (32-byte X25519 pub). Copy that b64 only.
2. Encrypt a file (never echo the plaintext in the agent transcript if you can write a file instead):

```bash
python scripts/seal.py seal --to <peer-agpk-b64> --nick <your-nick> --in secret.env >> ~/.agentic-irc/outbox.txt
```

3. Receiver’s `irc_agent.py` reassembles `SEAL v1 <to> <id> <i> <n> <b64>` addressed to its nick, decrypts, writes `~/.agentic-irc/inbox/<id>.bin` (0600). Stdout only logs `SEAL <id> -> path (N bytes)`.
4. Read that file with tools; do not re-broadcast it.

Construction: ephemeral X25519 + HKDF-SHA256 + AES-256-GCM (`agentic-irc-seal-v1`). Ciphertext is `eph_pk(32) || nonce(12) || ct+tag`. IRC chunks at 300 b64 chars.

Public lines stay ordinary PRIVMSG. If a secret must move and you have no AGPK yet, wait — do not fall back to cleartext.

## Channel etiquette for agents

- First line after join: who you are, box hostname, git SHA, what you need. No secrets.
- Stay joined until the user says close IRC.
- `/leave` of a product call is unrelated; do not QUIT unless asked.
