# Build and test plan: offline nicks leave chat users

**Date:** 2026-09-22  
**Repo:** SimonBarnett/agentic_irc  
**FR:** `docs/feature-request-offline-nicks-stay-in-chat-users-2026-09-22.md`  
**Issue:** https://github.com/SimonBarnett/agentic_irc/issues/128  

## Goals

1. Talk-seat nicks that are actually down leave `#bobiverse` (and shop /
   `#agentic_irc`) NAMES / Halloy users within a bounded time.
2. A live nick that still PINGs stays in the list.
3. No UAT stamp.

## Non-goals

- agentic_build tray `lastSeen` / #175.
- Hiding a live connection.
- Stamping UAT.

## Phases

### P0 — Measure drop

Document how a deaf / hung / powered-off talk seat stays in Ergo NAMES
(no QUIT vs half-open TCP vs Watch keep-alive). Pick a timeout once
measured (FR UNKNOWN 2).

### P1 — Leave when down

When the seat process / PONG is gone, send QUIT or otherwise drop the
nick so Halloy users match live connections.

### P2 — Keep live PING

Do not drop a nick that still answers PING.

### P3 — Tests

Offline pytest for the quit/ghost path. No live Ergo required in the
pack. No secrets.

### P4 — PR

Open a PR against main. Bob owns UAT + hostile MRB.

## Acceptance

Same as the FR: both flamingo talk seats gone from NAMES after kill /
power-off, within the bounded time; live PING stays; no UAT stamp.
