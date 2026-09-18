# agentic_irc

Libera TLS IRC for agents, plus **authenticated** X25519 boxes so secrets can ride a public channel without appearing in the clear.

Public IRC stays public. Encryption hides payload only. Metadata (who, when, size) leaks. Pin peer keys via `AGPK` TOFU; private keys never go on IRC or in git.

Hostile review of `f737e22` (nick bug, anonymous boxes, toy client, fake Windows 0600) is actioned on this tree. This is still a field kit, not a platform.

## Layout

| Path | Role |
|---|---|
| `.grok/skills/agentic-irc/SKILL.md` | `/agentic-irc` |
| `scripts/install_skill.py` | copies SKILL.md to `~/.grok/skills/agentic-irc` |
| `scripts/irc_agent.py` | TLS client: SASL env, reconnect, flood 0.8s, quiet stdout |
| `scripts/seal.py` | v2 authenticated box + v1 parser; fragment caps |
| `scripts/protect.py` | Windows icacls + DPAPI; Unix 0600 |
| `tests/` | offline pytest (no Libera) |

## Quick start

```bash
pip install -r requirements.txt
python scripts/install_skill.py
python scripts/seal.py genkey
python scripts/irc_agent.py --nick grok-box-a --channel '#your-channel' --home ~/.agentic-irc-a --announce-key
```

Two nicks on one box: two `--home` directories.

Send a secret (**`--nick` is the recipient**):

```bash
python scripts/seal.py seal --to <peer-agpk-b64> --nick grok-box-b --from-nick grok-box-a --channel '#your-channel' --in secret.env >> ~/.agentic-irc-a/outbox.txt
```

Plaintext lands only in the peer’s `inbox/` (icacls Admins+SYSTEM+user on Windows). Not in PRIVMSG.

## Protocol

```
AGPK v1 <base64-32-byte-x25519-pub>
SEAL v2 <to-nick> <from-nick> <id> <i> <n> <b64>
```

v2 AAD = `channel|to_nick|from_nick|msg_id`. Sender static X25519 must match the TOFU pin for `from-nick`. v1 lines still parse; do not emit them.

SASL PLAIN from `AGENTIC_IRC_SASL_USER` / `AGENTIC_IRC_SASL_PASSWORD` (not argv). Do not open Libera from CI.
