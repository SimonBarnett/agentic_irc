# Build and test plan — shop channels + write-only digest

**Repo:** SimonBarnett/agentic_irc
**Spec:** docs/feature-request-shop-channel-worker-cc-webhook-2026-09-21.md
**Issue:** #46
**Sister:** agentic_build #124
**Status:** intake — implement after Bob dispatches

## Goals

1. Digest merge + `!bobiverse` reader from file (no HTTP GET).
2. Worker nick / shop name helpers (`flamingo:4412` → `w-fl-4412` / `#flamingo`).
3. QUIT of `w-*` deletes worker; QUIT of `bob-*` sets machine offline and
   empties workers (shop-down).
4. Scrub `!report` ingest. Offline pytest only.

## Non-goals

Live Ergo from CI. Public digest GET. Implementing the ionos listener
in this repo if sister lands it first — then this repo only consumes
`digest.json`.

## Phases

### P0
Read FR + current `scripts/` / `bob-irc` skill.
Record whether #36 `!report` parser already exists.

### P1
Helpers + digest schema tests (merge, delete-worker, shop-down,
offline persist).

### P2
`!bobiverse` / `!bobiverse ?` / `!bobiverse <id>` whisper formatter.
`!report` → ERR line, no merge.

### P3
Skill + docs/README.md live index. Do not point at mrb PDFs.

### P4
Push `work/shop-channel-digest`. Hostile MRB on #46. Bob UAT only.

## Done

- [x] FR + this plan on the branch (intake)
- [ ] pytest green, no sockets
- [ ] #36 write verbs documented as scrubbed
- [ ] Completion does not self-stamp UAT
