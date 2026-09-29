# airc-console: ChanServ shop vs domain/workgroup lobby (FR #314)

**Repo:** https://github.com/SimonBarnett/agentic_irc  
**Issue:** https://github.com/SimonBarnett/agentic_irc/issues/314  
**Surface:** `airc_console_service.py`, `airc_console.py`

## Problem

Always joining `#{machinename}` as `console-<machine>` creates orphan shop channels when the machine channel is **not** ChanServ-registered. Those boxes should instead lobby on the shared domain/workgroup channel under the bare machine nick.

## Behaviour

After IRC registration (`001`), probe ChanServ for `#{machinename}` (timeout ~8s).

| ChanServ result | Channel | Nick |
|---|---|---|
| **Registered** | `#{machinename}` | `{machinename}_console` |
| **Not registered** / probe timeout / no ChanServ | `#{domain_or_workgroup}` | `{machinename}`, then `{machinename}_1`, `_2`, … on `433` |

- Domain/workgroup: Windows `Domain` when domain-joined, else `Workgroup`, cleaned like `machine_id` (non `[A-Za-z0-9_-]` → `-`). Override: `AIRC_CONSOLE_DOMAIN` / `--domain`.
- NickServ GUID in `~\.airc-console\console.password` is **reused** (issue #271) for whichever nick is chosen; IDENTIFY/REGISTER still best-effort.
- Shop silence CAST IRON unchanged: no PRIVMSG on the joined channel; Query/NOTICE only.
- Explicit `--nick` / `--channel` (if provided) bypass auto selection for that session.

## Probe

```
PRIVMSG ChanServ :INFO #<machinename>
```

Treat as **registered** if the reply indicates an existing registration (e.g. contains `registered` and does not say `is not registered` / `isn't registered` / `not found`).  
Treat as **not registered** on explicit not-registered text, empty ChanServ, or timeout.

Probe nick for the `001` handshake is `{machinename}_console` (unique enough on shared Ergo). After the probe, `NICK` may change for lobby mode before `JOIN`.

## Acceptance

- [ ] ChanServ-registered shop → JOIN `#{machine}` as `{machine}_console`
- [ ] Not registered / timeout → JOIN `#{domain}` as `{machine}` (or `_{n}` after 433)
- [ ] Same `console.password` GUID used across modes
- [ ] Hermetic unit tests for domain clean + mode selection + 433 lobby suffix
- [ ] Docs/skill mention FR #314

## Non-goals

- Registering the shop with ChanServ automatically
- Speaking on the lobby/shop channel
- Changing operator allowlists (`bob-*` / operators.txt stay as today)
