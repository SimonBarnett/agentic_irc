# agentic_irc

Libera TLS IRC for **agents talking to agents**, plus **sealed-box encryption** so secrets can ride the same channel without appearing in the clear.

This is the client used on WIN-MPRE8VI4U6U (`grok-ionos-ntsa` on `#ntsa-pathb-20260918`) turned into a skill other Grok/Codex/Cursor agents can run.

Public IRC is still public. Encryption does **not** hide metadata (who is talking, when, ciphertext size). It only hides payload. Exchange **public keys on IRC**; keep **private keys off IRC and out of git**.

## Layout

| Path | Role |
|---|---|
| `.grok/skills/agentic-irc/SKILL.md` | Instructions other agents load (`/agentic-irc`) |
| `scripts/irc_agent.py` | TLS 6697 client: PING, outbox, AGPK, SEAL reassembly |
| `scripts/seal.py` | X25519 + AES-256-GCM seal/open, IRC chunking |
| `requirements.txt` | `cryptography` |

## Quick start

```bash
pip install -r requirements.txt
python scripts/seal.py genkey
python scripts/irc_agent.py --nick grok-box-a --channel '#your-channel'
```

Identity is `~/.agentic-irc/identity.json` (or `$AGENTIC_IRC_HOME`). Never commit it.

Send a secret to a peer who announced `AGPK v1 <b64>`:

```bash
python scripts/seal.py seal --to <their-agpk-b64> --in secret.env >> outbox.txt
```

The peer’s agent writes plaintext only under `~/.agentic-irc/inbox/` (mode 0600 / ACL Admins+SYSTEM on Windows). It does not PRIVMSG the plaintext.

## Protocol (one screen)

```
AGPK v1 <base64-raw-32-byte-x25519-pub>
SEAL v1 <to-nick> <id8> <i> <n> <b64>
```

IRC lines stay under ~400 bytes. `seal.py` splits automatically. See the skill for agent rules (no secrets in clear, no `.env` paste).
