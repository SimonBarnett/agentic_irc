# Issue #128 — offline nick drop (P0 measure)

**Date:** 2026-09-22

## Symptom

Talk-seat nicks (`flamingo-<seatPid>`, etc.) stayed in Ergo `#bobiverse` NAMES
after the seat stopped answering. Halloy user lists matched Ergo NAMES, so
offline flamingos looked present.

## Mechanisms (measured / inferred)

| Case | IRC session | Fix in this PR |
|------|-------------|----------------|
| Coordinator PowerShell (`seat=`) exits while detached `irc_agent` keeps running | Nick stays until TCP ends | `irc_agent` polls the talk-seat coordinator PID (nick suffix, or `coordinator.pid` `seat=` when readable); sends `QUIT` when gone (default 15s, `AGENTIC_IRC_SEAT_LIVENESS_S`) |
| `Stop-Process -Force` on `irc_agent` | No `QUIT` → ghost until Ergo TCP timeout | `Start-TalkSeat` stops agent with non-force first (~600ms) so SIGTERM handler can `QUIT` |
| Box power-off / half-open TCP | Server-side ping timeout (Ergo-specific; not measured in CI) | Out of agent scope; bounded by Ergo ping settings |

Live seats that still answer server `PING` with `PONG` are unchanged. Liveness
only drops the nick when the coordinator seat process is gone.

## Bounded time

Client-side: up to `AGENTIC_IRC_SEAT_LIVENESS_S` (default 15s, clamp 3–120s)
after the coordinator exits. Ergo may add server ping interval on silent TCP.
