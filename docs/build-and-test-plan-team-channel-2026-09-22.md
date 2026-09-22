# Build-and-test plan: `#agentic_irc` team channel (2026-09-22)

**FR:** `docs/feature-request-team-channel-2026-09-22.md`

## Channel

LOCKED: `#agentic_irc`.

## When Simon says go

1. Create/register `#agentic_irc` on ionos Ergo (ACL/topic as Simon specifies).
2. Document in `docs/` + `.grok/skills/bob-irc` / `agentic-irc` (who JOINs; `bob-*` out).
3. Optional: `Start-TalkSeat` / config flag to append `#agentic_irc` without dropping shop.
4. Offline pytest for channel-list helpers; do not open IRC from CI.
5. Open PR; hostile MRB; no UAT until Bob stamps.
