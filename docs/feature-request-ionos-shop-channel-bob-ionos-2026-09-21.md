# Feature request: `#ionos` shop — `bob-ionos` + all ionos workers

**Date:** 2026-09-21  
**Repo:** https://github.com/SimonBarnett/agentic_irc  
**GitHub issue:** https://github.com/SimonBarnett/agentic_irc/issues/70  
**Raised by:** Simon  
**UAT + hostile MRB owner:** Bob  
**Related:** #46 shop channels, `agentic_build/config/bobiverse.json` (`ionos` → `bob-ionos`)

## Problem

On the **ionos** fleet seat, humans and agents need a dedicated shop room
`#ionos` (machine id `ionos`, not the Windows hostname). **`bob-ionos`**
is the Bob / Grok builder agent for that box. Every **ionos worker**
(`w-io-<pid>`) and **`bob-ionos`** must be present in `#ionos` so shop
traffic, `working_on` lines, and worker conversation stay off `#bobiverse`.

Today `channels_for_nick` already maps `bob-ionos` → `#bobiverse` + `#ionos`
and `w-io-*` → `#ionos` only, but production logs have shown reconnects that
only `JOIN #bobiverse`, and ionos-side worker agents are not always started
with the shop JOIN path.

## LOCKED

1. Shop channel name is `#ionos` (machine id `ionos` in `bobiverse.json`).
2. **`bob-ionos`** — ionos Bob/Grok fleet agent — JOINs **`#bobiverse`**
   and **`#ionos`**, stays on both while Watch-Bobiverse runs.
3. **All ionos workers** — IRC nicks `w-io-<pid>` — JOIN **`#ionos` only**
   (never `#bobiverse`). Same rules as #46 for other shops.
4. Do not rename `bob-ionos`. Do not use Libera. Private Ergo
   `irc.ntsa.uk:6697` only.
5. Ergo must allow/register `#ionos` for registered fleet nicks (with
   `#bobiverse`).

## Gap vs current tree

| Area | Now | Want |
|------|-----|------|
| `bobreport.channels_for_nick` | bob-* → fleet + shop | Keep; prove on ionos |
| `irc_agent.py` JOIN | Multi-channel JOIN | Reliable `#ionos` after reconnect |
| `Install-BobIrc` / Watch | Starts `bob-ionos` | Document + verify dual JOIN |
| Worker IRC on ionos | Often no `w-io-*` client | Spawn/join when git worker runs |
| Docs / skills | Shop list includes `#ionos` | State clearly: bob-ionos = ionos grok seat |

## MUST

1. After `Install-BobIrc -MachineId ionos` and Watch recycle, Ergo log or
   `irc.log` shows `bob-ionos` **JOIN #bobiverse** and **JOIN #ionos**
   on the same session (no shop-only drift on reconnect).
2. When an ionos git worker runs with IRC worker home under
   `~\.agentic-irc-bobiverse\workers\ionos\<pid>`, that worker’s
   `irc_agent` JOINs **#ionos** as `w-io-<pid>`.
3. Offline pytest: ionos nick table — `bob-ionos` channels include `#ionos`;
   `w-io-4412` channels are `[#ionos]` only.
4. Skills `bob-irc` / `agentic-irc`: one line that **bob-ionos** is the
   ionos Bob/Grok agent and **`#ionos`** is its shop with all `w-io-*`.

## MUST NOT

- Move fleet POINT/ACTION firehose into `#ionos`.
- Join workers to `#bobiverse`.
- Break other shops (`#flamingo`, `#marchhare`, `#ce-priority-dev1`).

## Acceptance

1. Halloy (or log): `NAMES #ionos` lists `bob-ionos` and each live
   `w-io-*` for jobs on ionos.
2. `pytest -q` includes ionos shop JOIN/channel tests (extend
   `test_bobiverse_talk` or `test_bobreport`).
3. House-clean doc cross-link in `agentic_build/docs/bobiverse.md` shop
   table (sister note only; no UAT stamp in this FR).

## Out of scope

- Sister Watch `reportUrl` (#124 on agentic_build).
- Grok-talk inbox worker (separate FR/PR).
