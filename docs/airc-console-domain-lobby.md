# FR - airc console ChanServ shop vs domain lobby

**Issue:** https://github.com/SimonBarnett/agentic_irc/issues/314

## Goal

On connect, choose nick and channel from whether `#{machinename}` is
**ChanServ-registered** on Ergo:

| Shop `#{machinename}` | Channel | Nick | NickServ |
|----------------------|---------|------|----------|
| **Registered** | `#{machinename}` | `{machinename}_console` | IDENTIFY/REGISTER with existing `console.password` GUID |
| **Not registered** / probe timeout | `#{domain_or_workgroup}` for that session only | `{machinename}`, then `{machinename}_1`, `_2`, ... on 433 | Same GUID after nick settles |

## Behaviour

1. Resolve fleet `machinename` (`AIRC_CONSOLE_MACHINE` / `BOB_MACHINE_ID` / ...).
2. Resolve domain/workgroup (`--domain` / `AIRC_CONSOLE_DOMAIN` / Windows join;
   never block unbounded on WMI).
3. Connect provisionally as `{machinename}_console`.
4. After `001`, `PRIVMSG ChanServ :INFO #{machinename}` (timeout 8s -> lobby).
5. Registered -> JOIN shop as `{machinename}_console`.
6. Missing -> `NICK` to `{machinename}` (433 -> `_1`, `_2`, ...), REGISTER/IDENTIFY,
   JOIN `#{domain_or_workgroup}` only (do not also create `#{machinename}`).
7. Stay silent on the chosen channel; Query shell unchanged.

Forced modes: `--shop-mode registered|domain-lobby|auto` (env
`AIRC_CONSOLE_SHOP_MODE`).

## Acceptance

| Gate | Proof |
|------|-------|
| ChanServ registered fixture | nick `{machine}_console`, channel `#{machine}` |
| ChanServ missing / timeout | channel `#{domain}`, nick `{machine}` then `_1` on 433 |
| NickServ GUID | reuse `~\.airc-console\console.password` |
| Offline | `pytest tests/test_airc_console_fr253.py` + `--selftest` |
| Live smoke | service log shows `shop-mode=` + JOIN; operator Query still pipes |

## Non-goals

- ChanServ REGISTER of `#{machinename}` by the console
- Mode 3 / DUMB / `#bobiverse`
- Human UAT stamp from CI alone

## Layout

- `scripts/airc_console.py` - helpers + `parse_chanserv_info`
- `scripts/airc_console_service.py` - probe / JOIN state machine
- `.grok/skills/airc-console/SKILL.md`

## Issue #321

Do not block JOIN on a NICK echo after switching to the lobby nick. Ergo may
omit the confirmation; optimistic NICK then JOIN, re-JOIN on 433.
