# agentic_irc

Libera TLS IRC for two operators. Secrets are **TOFU-pinned DH-AAD** boxes on a public channel (not signatures; first AGPK for a nick wins). Payload is hidden; who/when/size leak.

Envelope: two homes, one **private** Libera channel, humans watching the first AGPK pin. Secrets must be rotatable if the log is dumped. Unattended public channels are out of scope.

Field kit, not a platform.

## Layout

| Path | Role |
|---|---|
| `.grok/skills/agentic-irc/SKILL.md` | `/agentic-irc` |
| `.grok/skills/invite-airc/SKILL.md` | `/invite-airc` — chair `--chair` copy-paste thin invite |
| `scripts/install_skill.py` | copies SKILL.md + scripts + requirements |
| `scripts/irc_agent.py` | TLS client: reconnect, flood 0.8s, quiet stdout, SIGINT |
| `scripts/seal.py` | v2 TOFU-DH-AAD + v1 parser |
| `scripts/protect.py` | Windows icacls + DPAPI; Unix chmod (raises on failure) |
| `src/moot_thin/` | Mode 3 `airc-moot-thin.exe` (Win32 ANSI; Schannel; DUMB jobs + moot JOIN) |
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

## Libera SASL / which box

AWS → Libera requires SASL with a **verified NickServ** account. Without it the AWS Grok Bot box never gets numeric `001`. Prefer **IONOS** for unattended mode-1 until those accounts exist.

SASL is env-only: `AGENTIC_IRC_SASL_USER` and `AGENTIC_IRC_SASL_PASSWORD`. Do not put assignments in commits or prompts. If those env vars are unset, the client logs `INFO no-sasl` and sends `CAP END` so registration can proceed unauthenticated.

## Wrong first AGPK pin (TOFU)

First AGPK for a nick wins. If the wrong key was pinned (for example you announced another agent's AGPK as your own), wipe `$AGENTIC_IRC_HOME/peers.json` on the **receiver** and restart the receiver. Later correct AGPKs are ignored as mismatch. Do not announce the wrong AGPK.

## Extensions

Still a field kit. Still a **private** channel. Unattended public channels stay out of scope.

| Verb | Skill | Role |
|---|---|---|
| `MOOT v1` | `/agentic-moot` | Chair, roster, floor. Do not SAY unless you hold the floor. |
| `FILE v1` | `/agentic-file` | Tier S = SEAL; M = clear CHUNKs (not secret); L = path drop. |
| `DUMB v1` / `CAPA v1` | `/agentic-dumb` | Allowlisted connector. `--operators` required. Jail. PSK off-channel. |
| Mode 3 thin CLI | `airc-moot-thin.exe` | Native Win32 ANSI moot member. Same DUMB jobs. Zero-arg: click the exe / enter PIN (chair `--chair` prints a copy-paste `--pin --channel --moot` line, expires 10m). `--operators` required for unattended `--key` installs. Release tag `mode3-thin`. Win95 TLS **not** claimed. |
| Invite elder box | `/invite-airc` | Operator copies `airc` and runs the one line `--chair` printed. See `.grok/skills/invite-airc/SKILL.md`. |

Python reference: `scripts/dumb_agent.py` (stdlib socket+ssl listen: connect/join/flood/CAPA/jobs; jail + PSK). Operators drive it with `dumb_ctl.py`. Server 2012 adapter: `src/dumb_dotnet/airc-dumb.exe` is a behaviour-compatible net45 clone (TcpClient + SslStream TLS 1.2, CAPA, PSK DUMB v1 ping/sysinfo/exec/get/put, jail, unknown-operator drop with no result ciphertext, truncated exec spill). Python remains the protocol reference. Empty `--operators` is refused. Build: `src/dumb_dotnet/build.bat` or `msbuild airc-dumb.csproj /p:Configuration=Release /p:TargetFrameworkVersion=v4.5`. No runtime NuGet for crypto. TLS 1.2 preflight (`SchUseStrongCrypto`) is in the skill and `src/dumb_dotnet/README.md`. Wrapper: `airc-dumb.cmd`. Offline pytest: set `DOTNET_DUMB_EXE`. CI does not open Libera. Not claimed ready for human UAT.

Mode 3 native client lives in `src/moot_thin/` (`airc-moot-thin.exe`, GitHub Release `mode3-thin`). Chair `--chair` prints a ready-to-copy thin invite (`--pin`, `--channel`, `--moot`, expires 10m). Field box: copy the `airc` folder and run that one line (or click the exe and enter the PIN). Ritual: `.grok/skills/invite-airc/SKILL.md`. `--key` remains the air-gap path. It is not a Phase 5 .NET port. It does **not** claim Windows 95 TLS; see `docs/mode3-tls-spike.md`, `docs/mode3-os-matrix.md`, and `docs/mode3-zero-config-2026-09-19.md`. Not claimed ready for human UAT on the zero-config path until Bob re-MRBs it.
