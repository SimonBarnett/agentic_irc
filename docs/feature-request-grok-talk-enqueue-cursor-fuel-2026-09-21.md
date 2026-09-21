# Feature request: Grok-talk enqueue when Cursor Models remaining > 0

**Date:** 2026-09-21
**Repo:** https://github.com/SimonBarnett/agentic_irc
**Sister:** https://github.com/SimonBarnett/agentic_build#126 (Watch-GrokTalk /
`Invoke-BobGrokTalkTick` already consumes inbox when Cursor remaining > 0)
**Raised by:** Hostile MRB of agentic_irc SHA `a083f531f648db2dea43def5a79a45cefbf48d4a`
(PR #67) against #56
**Related:** #56 / PR #60 (hook: enqueue only when peer `weekly` > 0),
agentic_build#126 / #128 (sister worker + fleet install)
**UAT + hostile MRB owner:** Bob

## Problem

#56 PASS-nits (PR #60) made the IRC hook enqueue `grok-inbox.jsonl` only when
peer `weekly` > 0. Ionos often has Grok Build weekly = 0. Sister #126 will
start a listen-talk job when **Cursor Models remaining > 0**, but it has
nothing to read: `irc_agent` never wrote the inbox line. Addressed English
still stops at the canned ACK (`weekly=0 (cannot grok-talk)`).

#56 UNKNOWN said Cursor Models at weekly=0 is **sister policy, not IRC
protocol**. That layering is why the sister consumer is blind on weekly=0
seats. The hook must enqueue when the sister would have fuel.

PR #67 tried this in-tree and is **out of scope for this park**. Do not copy
it: it treated any `cursor_label` (including billing display `-£75`) as fuel,
broke #56 AC2 / LOCKED #5, and added a second Python worker
(`grok_talk_worker.py`) that races Watch-GrokTalk.

## LOCKED

1. Keep #56 AC2 for **no fuel**: grok-talk disabled, or weekly=0 **and**
   Cursor Models remaining = 0 → ACK only. No inbox line.
2. Enqueue when `grok_talk_enabled` (or `AGENTIC_IRC_GROK_TALK=1`) **and**
   (peer `weekly` > 0 **or** Cursor Models remaining > 0). Remaining comes
   from the same sister numbers Watch-GrokTalk uses
   (`Get-BobCursorAgentWeeklyRemaining` / `remaining_pct`), not from a
   display `cursor_label` being non-empty.
3. Do not treat `cursor_label` strings (`-`, `empty`, `-£75`, on-demand
   overage text) as fuel. Label is tray/POINT display.
4. When enqueue will fire, the #54 ACK must **not** say `cannot grok-talk`.
5. Update `docs/grok-talk-envelope-v1.md` and `bob-irc` / `agentic-irc`
   skills so they match the gate. Default `grok_talk_enabled` stays false.
6. **No second consumer in this repo.** Completions stay sister
   Watch-GrokTalk / `Invoke-BobGrokTalkTick`. Do not add
   `grok_talk_worker.py` (or equivalent) that calls cursor-agent / grok.exe.
7. Same mention eligibility as #56 (not protocol, not `bob-*` asker,
   cooldown, max 1 pending job). Watch-Bobiverse stays no grok.exe.
8. Offline pytest. No live Ergo. No live grok. PR only. Bob stamps UAT.

## UNKNOWN

- How IRC reads Cursor remaining without importing BobBridge (peer JSON
  field vs a small sister file vs env). Must be a remaining percent, not a
  label.
- Shop `#ionos` vs `#bobiverse` only — honour existing `reply_target`.

## Gap vs tree (`#56` merged hook)

| Current | Wanted |
|---|---|
| `weekly_fuel_ok` only (`weekly` > 0) | Also enqueue when Cursor remaining > 0 |
| ACK `weekly=0 (cannot grok-talk)` always | That text only when grok-talk will not enqueue |
| Envelope / skills: fuel is weekly > 0 | Same text as LOCKED 1–2 |
| Sister #126 idle on ionos | Inbox line present so Watch-GrokTalk can run |

## Acceptance

- **AC1** Enabled + weekly=0 + Cursor remaining > 0 (test double) → inbox
  line; ACK does not say `cannot grok-talk`.
- **AC2** Enabled + weekly=0 + Cursor remaining = 0 (or missing) → no inbox;
  ACK matches #54. Non-empty `cursor_label` alone is not enough.
- **AC3** Disabled still ACK-only. Protocol / `bob-*` / `!bobiverse` never
  enqueue.
- **AC4** Pytest green. Envelope + skills match the gate. No
  `grok_talk_worker.py` (or other grok.exe/cursor-agent consumer) in this
  repo. No `password=` / `XAI_API_KEY=` assignments.

## Non-goals

- Replacing sister Watch-GrokTalk / BobBridge worker.
- LLM inside `Watch-Bobiverse.ps1` or `irc_agent` ACK path.
- Changing #56 weekly>0 enqueue.
- MRB PDF.
