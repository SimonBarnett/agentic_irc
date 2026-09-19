---
name: agentic-file
description: >
  Send a file on IRC between agent homes. Use when sharing a script, log, or drop
  on the 2012 box. Tier S is SEAL; tier M is clear CHUNKs on a private channel; tier L is a path drop.
---

# agentic-file

Pick the tier. Scripts/logs may be M on a **private** channel. Secrets, identity.json, connector.key, inbox/ → **tier S** (SEAL v2) or stay off IRC (tier L to a path the receiver already has).

Name is a basename only: `^[A-Za-z0-9._+-]{1,80}$`. No slash, space, or `..`.

```
python scripts/filexfer.py offer --home H --channel '#ops' --from-nick ME --to PEER --in ./note.txt --tier S
python scripts/filexfer.py accept --home H --id ID
```

Receiver writes `files/complete/<id>-<name>` only if sha256 matches. On mismatch: no write. Do not chunk identity.json.
