# Build and test plan: `#ionos` shop — `bob-ionos` + ionos workers

**FR:** `docs/feature-request-ionos-shop-channel-bob-ionos-2026-09-21.md`

## Phase 1 — Prove JOIN path

- Trace `irc_agent` reconnect: `_pending_joins`, multi-channel `JOIN`, 366/JOIN echo.
- Fix if `bob-ionos` ever runs with a single-channel list on ionos.
- Confirm Ergo has `#ionos` (operator doc note in `bobiverse-ionos-ircd.md` if needed).

## Phase 2 — Worker shop JOIN on ionos

- Find where git workers start `irc_agent` (agentic_build bridge / worker home).
- Ensure machine id `ionos` → worker nick `w-io-<pid>` and shop `#ionos`.

## Phase 3 — Tests + docs

- Pytest: `channels_for_nick('bob-ionos', '#bobiverse')` → `#bobiverse`, `#ionos`.
- Pytest: worker nick → `#ionos` only.
- Update `.grok/skills/bob-irc/SKILL.md` (and harvest to agentic_build if required).

## Evidence for MRB

- `pytest -q` relevant files.
- Redacted `irc.log` snippet: two JOINs for `bob-ionos` after Watch recycle.
- No live Halloy required in CI.
