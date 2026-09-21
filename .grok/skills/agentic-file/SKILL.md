---
name: agentic-file
description: >
  Send a file on IRC between agent homes. Use when sharing a script, log, or drop
  on the 2012 box. Tier S is SEAL; tier M is clear CHUNKs on a private channel; tier L is a path drop.
---

# agentic-file

Pick the tier. Scripts/logs may be M on a **private** channel. Secrets, identity.json, connector.key, inbox/ → **tier S** (SEAL v2) or stay off IRC (tier L to a path the receiver already has).

Name is a basename only: `^[A-Za-z0-9._+-]{1,80}$`. No slash, space, `..`, or drive letters. Tier S plaintext inside SEAL v2 is an `AIRC-FILE v1` envelope (name/bytes/sha256/mode, then a blank line, then raw bytes). Receiver decodes the envelope and writes `files/complete/` only if the basename jail, sha256, and length match.

`--home` is on the **parent** command, before the subcommand:

```powershell
$ircHome = "$env:USERPROFILE\.agentic-irc-cursor"   # not $home — shadows $HOME in PowerShell
$env:AGENTIC_IRC_HOME = $ircHome
python scripts/filexfer.py --home $ircHome offer `
  --channel '#bobiverse' --from-nick cursor-ionos --to flamingo-17568 `
  --in "$env:USERPROFILE\.grok\bob\report.secret" --tier S
python scripts/filexfer.py --home $ircHome accept --id <fid-from-stdout>
```

Tier **S** emits `FILE v1 OFFER` plus `SEAL v2` lines into `outbox.txt` (one append,
newline-terminated). Recipient must have sender AGPK pinned in `peers.json`.
Coordinator `irc_agent` on that home drains the outbox.

Fleet: ionos sends `report.secret` to a peer session nick (`flamingo-17568`,
`bob-flamingo`, …) when Simon asks on `#bobiverse` — never cleartext on channel.
Include `reportUrl=http://bob.ntsa.uk/bob/v1/report` in a separate SEAL or a
small env file if the peer needs both.

Receiver writes `files/complete/<id>-<name>` only if sha256 matches. On mismatch: no write. Do not chunk identity.json.
