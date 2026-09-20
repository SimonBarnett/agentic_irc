---
name: invite-airc
description: >
  Invite an elder/field Windows box into an agentic_irc Mode 3 moot with a
  copy-pasteable thin command that includes a PIN. Use when Simon or an agent
  says invite airc, elder machine, copy airc and run, PIN invite, or /invite-airc.
  Chair runs on a modern box; thin is double-click-averse — one command only.
---

# Invite airc (elder machine)

## Operator ritual (LOCKED)

1. Operator asks the **agent** for a command (includes PIN).
2. Operator copies the `airc` folder (exe + optional ini) onto the elder box.
3. Operator runs **that one command** on the elder box.

Do **not** require flag soup, interactive PIN hunting, or hand-edited 8-arg lines as the happy path.

## Agent steps (chair / modern box)

1. Prefer release `mode3-thin` / `airc-moot-thin.exe` >= 0.2.1 (chair prints the thin invite).
2. Start chair invite on the modern box (IONOS Ergo `irc.ntsa.uk:6697`, or `--host` if the thin still targets another net):

```bat
airc-moot-thin.exe --chair --channel "#YOUR-PRIVATE-CHAN" --nick cm-bob
```

3. Capture stdout. `--chair` prints a ready-to-copy thin line plus PIN / moot / channel / expires (TTL 10m).
4. Hand the operator **that one line** to run after copying `airc`. Shape:

```bat
airc-moot-thin.exe --pin NNNNNN --channel "#YOUR-PRIVATE-CHAN" --moot 16hex
```

Self-heal fills nick/home/jail from the box. Optional: `--hello`.
5. Confirm thin JOIN + CAPA on chair; then sealed smoke (`exec hostname`) if requested.
6. Never paste long-term PSK into chat. PIN is ephemeral (TTL ~10m).

## Hard rules

- Win95/98/NT4/XP live IRC still not claimed.
- Empty operators refused for unattended installs; after PIN pair, chair becomes operator.
- Do not commit `connector.key` or live PINs.
- `--chair` stdout includes the copy-paste thin one-liner (`--pin`, `--channel`, `--moot`) and an expires note.
