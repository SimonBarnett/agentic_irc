---
name: invite-airc
description: >
  Invite an elder/field Windows box into an agentic_irc Mode 3 moot by
  publishing live join details and double-clicking the thin exe. Use when
  Simon or an agent says invite airc, elder machine, zero config, beacon,
  publish details, PIN invite, or /invite-airc. No copy-paste flag soup on
  the field box.
---

# Invite airc (elder machine) — double-click

## Operator ritual (LOCKED)

1. Agent on the modern box starts the chair and **publishes** the invite
   (`airc-invite.json` beside the exe, or a secret gist URL in `beacon.url`).
2. Operator copies the `airc` folder onto the elder box **once**
   (exe + `airc-invite.json` and/or `beacon.url`).
3. Operator **double-clicks** `airc-moot-thin.exe`. Nothing to type.

Do **not** require `--pin --channel --moot` or `Enter PIN:` as the happy path.
Those remain fallbacks.

## Agent steps (chair / modern box)

1. Prefer release `mode3-thin` / `airc-moot-thin.exe` >= 0.3.0.
2. Start chair on the modern box (fleet: IONOS Ergo; else pass `--host`):

```bat
airc-moot-thin.exe --chair --channel "#YOUR-PRIVATE-CHAN" --nick cm-bob --host irc.ntsa.uk
```

3. `--chair` writes `airc-invite.json` and `airc-invite.ini` next to the exe
   (PIN + channel + moot + expiry; **no** PSK). TTL 10 minutes. It still prints
   the copy-paste `--pin` line as a fallback.
4. Optional live bulletin (so a folder already in the field can refresh):

```bash
python scripts/beacon.py make --channel '#YOUR-PRIVATE-CHAN' --moot <16hex> --pin <6digit> --pair <16hex> --chair cm-bob --out-dir /path/to/airc --gist
```

That writes `beacon.url` (secret gist, `https://` only). Needs `gh`.
5. Tell the operator: copy `airc`, double-click the exe.
6. Confirm thin JOIN + CAPA on chair; sealed smoke (`exec hostname`) if asked.
7. Never paste long-term PSK. Never commit `airc-invite.json` or live PINs.
   If the invite expired, run `--chair` again and overwrite the files.

## Hard rules

- The invite file / gist URL **is** the 10-minute secret. Private channel still required.
- Win95/98/NT4/XP live IRC still not claimed.
- Empty operators refused for unattended `--key` installs; after pair, chair becomes operator.
- Already-paired boxes (`dumb\connector.key` + `dumb\paired.ini`) reconnect and ignore a new beacon.
- Fallback: `airc-moot-thin.exe --pin NNNNNN --channel "#chan" --moot 16hex`
- Do not commit `connector.key` or live PINs.
