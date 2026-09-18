# agentic_irc

Libera TLS IRC for two operators. Secrets are **TOFU-pinned DH-AAD** boxes on a public channel (not signatures; first AGPK for a nick wins). Payload is hidden; who/when/size leak.

Envelope: two homes, one **private** Libera channel, humans watching the first AGPK pin. Secrets must be rotatable if the log is dumped. Unattended public channels are out of scope.

Field kit, not a platform.

## Layout

| Path | Role |
|---|---|
| `.grok/skills/agentic-irc/SKILL.md` | `/agentic-irc` |
| `scripts/install_skill.py` | copies SKILL.md + scripts + requirements |
| `scripts/irc_agent.py` | TLS client: reconnect, flood 0.8s, quiet stdout, SIGINT |
| `scripts/seal.py` | v2 TOFU-DH-AAD + v1 parser |
| `scripts/protect.py` | Windows icacls + DPAPI; Unix chmod (raises on failure) |
| `tests/` | offline pytest (no Libera) |

## Quick start

```bash
pip install -r requirements.txt
python scripts/install_skill.py
python scripts/seal.py genkey
python scripts/irc_agent.py --nick grok-box-a --channel '#your-channel' --home ~/.agentic-irc-a --announce-key
```

Two nicks on one box: two `--home` directories.

`--nick` on `seal.py` is the **recipient**:

```bash
python scripts/seal.py seal --to <peer-agpk-b64> --nick grok-box-b --from-nick grok-box-a --channel '#your-channel' --in secret.env >> ~/.agentic-irc-a/outbox.txt
```

## Protocol

```
AGPK v1 <base64-32-byte-x25519-pub>
SEAL v2 <to-nick> <from-nick> <id16hex> <i> <n> <b64>
```

AAD = `lower(channel)|lower(to)|lower(from)|lower(id)` (no `|` in fields). IRC prefix nick must equal `from_nick` or the line is dropped. v1 parse only; do not emit v1.

`inbox/<id>.bin` existing skips overwrite of that id. Crypto-layer replay of SEAL lines is accepted. Do not open Libera from CI.
