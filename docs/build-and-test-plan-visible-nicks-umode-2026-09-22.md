# Build-and-test plan: visible talk-seat nicks (clear Ergo +i)

**FR:** `docs/feature-request-visible-nicks-umode-2026-09-22.md`
**MRB home:** https://github.com/SimonBarnett/agentic_irc/issues/110
**PR:** https://github.com/SimonBarnett/agentic_irc/pull/106

## Scope

Client-side `MODE <nick> -i` on `irc_agent` after 001, before JOIN. Talk
seats only. No Ergo server config. No Mode 3 DUMB.

## Steps

1. After `ready.wait` (001) and the existing 1s settle, send
   `MODE <live_nick> -i`, then `JOIN`.
2. Lock with offline pytest (source needle or mock-`send` order).
3. `pytest -q` green. CI must not open `irc.ntsa.uk`.
4. PR; hostile MRB on #110. Bob chairs live Halloy recycle.

## Success

- LOCKED 1–4 green on the review SHA.
- No `password=` / `XAI_API_KEY=` in git.
- Do not stamp UAT.

## Evidence expected

| Gate | Method |
|---|---|
| MODE `-i` before JOIN | `tests/test_agent.py` |
| Offline suite | `pytest -q` |
| CI | `.github/workflows/test.yml` |
| Live Halloy WHO / NAMES | Manual recycle; **not** CI |

## Non-goals

- Recycle of already-connected `+i` seats.
- `dumb_agent.py` umode.
- Human UAT stamp or MRB PDF.
