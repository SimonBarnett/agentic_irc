# Build and test plan: change-only webhook + chair

**FR:** `docs/feature-request-digest-webhook-chair-change-only-2026-09-21.md`

## Phase 1 — Protocol + callback

- Document POST body schema (delta fields, no heartbeat-only).
- `bobcallback` / `apply_callback`: no-op path, metrics log line.
- Remove or gate channel `BOB DIGEST` / fleet English from briefer path when chair enabled.

## Phase 2 — Chair seat

- `bobiverse.json`: `chairNick`, `chairHome` (or reuse ionos briefer home).
- Slim `irc_agent` flags or `bob-chair` entrypoint: JOIN `#bobiverse`, `!bobiverse` only.
- `Install-BobChair.ps1` (agentic_build) one-shot + Watch does not start chair.

## Phase 3 — Producer delta POST (with build #124)

- `Write-BobIrcStatus`: hash canonical peer blob; POST only on change.
- Test-Pack fixture: two ticks same data → zero POST.

## Phase 4 — Tests + skills

- `test_bobreport` / `test_bobcallback`: duplicate POST, whisper-only digest.
- Update `bob-irc` skill; harvest to agentic_build.

## MRB evidence

- pytest subset; redacted log: no `PRIVMSG #bobiverse :BOB DIGEST` in 5 min idle.
- One deliberate fuel change → one POST (Fake HTTP or integration test).
