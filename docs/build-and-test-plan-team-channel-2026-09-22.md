# Build-and-test plan: team Ergo channel (2026-09-22)

**FR:** `docs/feature-request-team-channel-2026-09-22.md`

## Blocked on

Simon confirms exact channel name (FR UNKNOWN).

## When unblocked

1. Register/create channel on ionos Ergo (ACL/topic as Simon specifies).
2. Document in `docs/` + `.grok/skills/bob-irc` / `agentic-irc` (who JOINs, bob-* out).
3. Optional: `Start-TalkSeat` / config flag to append team channel to `--channel` list without dropping shop.
4. Offline pytest for channel-list helpers; do not open IRC from CI.
5. Open PR; hostile MRB; no UAT until Bob stamps.
