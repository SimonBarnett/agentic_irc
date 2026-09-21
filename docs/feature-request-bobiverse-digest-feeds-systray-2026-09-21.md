# Feature request: `!bobiverse` must feed the Bob systray

**Date:** 2026-09-21  
**Repo:** https://github.com/SimonBarnett/agentic_irc  
**Sister (consumer):** https://github.com/SimonBarnett/agentic_build  
`docs/feature-request-bobiverse-digest-feeds-systray-2026-09-21.md`  
**Related:** #36 digest JSON, #46 shop/webhook, agentic_build#26 tray pull, agentic_build#91 cursor pools  
**Raised by:** Simon (Halloy / marchhare talk seat 2026-09-21 ~23:17 BST)  
**UAT + hostile MRB owner:** Bob  

Field kit. Private Ergo. Not a platform.

## Problem

A **bob** (`bob-*` Watch seat) must be able to send `!bobiverse` and receive
**all information required to paint the Bob fleet systray** (`Watch-BobTray` /
`Get-BobTrayHover`).

Today the chair whisper is a **presence digest**: online/offline, shop,
workers, `working_on`. That is not enough for the card:

- Per-machine **Grok weekly %** + **reset / period_end**
- Per-seat **Cursor Models** pool bars (label, %, reset, overage)
- **Job lines**: repo, sha, model, description, run-time (never `?` when known)
- **lastSeen** / idle vs running for tiles

Meanwhile `agentic_build` `Import-BobIrcTrayPull` only ingests whispers that
start with `BOB TRAY v1 …` (kv peer lines). Chair `BOB DIGEST v1` JSON is
not turned into `bob-peers\<id>.json` fields the tray reads. So Watch can
poll `!bobiverse` every ~120s and still leave the systray starved.

## LOCKED

1. When a **bob-*** (or Watch home nick) asks `!bobiverse`, the chair answer
   must carry **tray-complete** fleet state for every registry machine id
   (flamingo, marchhare, ionos, ce-priority-dev1).
2. Payload may stay whisper-only (no channel JSON dump). Chunk as
   `BOB DIGEST v1 i/n` and/or `BOB TRAY v1` lines — pick one stable shape
   and document it; do not require POINT firehose.
3. Minimum fields per machine (names may match existing peer JSON):
   `id`, `weekly`, `period_end` (or reset), `cursor_label`,
   `cursor_period_end`, `running`, `queued`, `lastSeen`, `jobs[]`
   (repo/sha/model/description/state/run_time when known), plus
   online/workers/`working_on` already in the digest.
4. Cursor **pool** rows (one per `bob-seats.json` seat) must be
   representable in the same pull (top-level `cursor_pools` or equivalent)
   so every box paints the same bars after one `!bobiverse`.
5. No secrets. No `password=` / report.secret in the digest.
6. Humans may still get the short English brief; agents/bobs must get the
   machine-readable tray payload (JSON and/or `BOB TRAY v1`).

## Gap vs current tree

| Current | Wanted |
|---|---|
| Digest = presence + workers | Digest = presence + **tray meters + jobs** |
| `Import-BobIrcTrayPull` needs `BOB TRAY v1` | Chair emit that **or** build ingest DIGEST → peers |
| Local `Write-BobIrcStatus` has weekly/cursor/jobs on disk only | Fleet share via `!bobiverse` pull |
| English whisper to talk seats | bob-* Watch must parse full tray set |

## Acceptance

1. `bob-marchhare` (or any bob-*) `!bobiverse` → whisper includes weekly +
   cursor + jobs for all four machines (offline machines still listed).
2. After one pull, `bob-peers\<id>.json` on that box is enough for
   `Get-BobTrayHover` to paint bars + job lines without POINT.
3. Offline pytest covers digest shape + tray ingest seam; no live Ergo in pack.
4. PR only; Bob stamps UAT.

## Non-goals

- Reintroducing channel POINT firehose.
- HTTP GET of digest.
- Changing Halloy.
