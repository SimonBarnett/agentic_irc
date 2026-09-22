# Issue #140 — offline nick FIX evidence

**Date:** 2026-09-22  
**MRB:** https://github.com/SimonBarnett/agentic_irc/issues/140  
**FR:** `docs/feature-request-offline-nicks-stay-in-chat-users-2026-09-22.md`  
**Git SHA:** `6003139` (branch `work/fix-issue-140-offline-nicks`)

## UNKNOWN 2 → LOCKED

| Case | Measured NAMES drop | Acceptance |
|------|---------------------|------------|
| Abrupt TCP close (RST, no QUIT) | **10 s** (`deadtcp-*`, 2026-09-22) | within **240 s** |
| Half-open / no PONG (stall read) | **15 s** (`halfopen-*`, 2026-09-22) | within **240 s** |
| Worst-case Ergo idle-timeouts | 90s ping + 150s disconnect (server config) | **240 s** cap |

## P1 mechanisms (no “out of agent scope” carve-out for box-off)

- Coordinator gone → `seat_liveness_loop` QUIT (unchanged green path).
- Recycle/kill → `agent_control.graceful_stop_agent` (`agent.quit.request`) before `Stop-Process` in `Start-TalkSeat.ps1`.
- Crash/kill with no agent → `bob-*` `talk_seat_ghost.maybe_prune_local_ghosts` (UNKNOWN 3 implemented).
- Deaf/hung → `seat_recv_idle_s` / `pong_grace_s` → QUIT.
- Box-off / half-open only → Ergo bound **240 s**; measured probes above are within bound.

## Live Ergo (redacted)

- Dead TCP: `docs/evidence/ergo-dead-tcp-measure.log`
- Half-open stall: `docs/evidence/ergo-half-open-measure.log`
- Live `flamingo-*` still in `#bobiverse` / shop / `#agentic_irc` while seats answer (Acceptance 2): `docs/evidence/issue-140-bobiverse-names-redacted.log`

Kill/power-off of production `flamingo-17568` / `flamingo-24108` is not re-run on this worker (seats were live at probe time). Client QUIT / ghost-prune paths are covered by offline pytest; Ergo drop bound is measured with throwaway nicks on the same Ergo.

## Tests

- `tests/test_offline_nick_liveness.py` — coordinator alive, dead PID, disable-env default, control QUIT, recv/PONG shutdown, `Start-TalkSeat` graceful stop wiring.
- `tests/test_talk_seat_ghost.py`, `tests/test_agent_control.py`

## UAT

No worker UAT stamp. Bob chairs MRB #140.
