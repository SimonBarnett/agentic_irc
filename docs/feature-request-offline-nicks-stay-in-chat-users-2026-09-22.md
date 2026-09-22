# Feature request: offline flamingo nicks stay in chat users

**Date:** 2026-09-22  
**Repo:** https://github.com/SimonBarnett/agentic_irc  
**GitHub issue:** https://github.com/SimonBarnett/agentic_irc/issues/128  
**Raised by:** Simon on `#bobiverse`  
**UAT + hostile MRB owner:** Bob  

## Problem

Simon: both flamingos are offline, but they still appear in the chat
user list. Live `#bobiverse` NAMES on this box still listed
`flamingo-24108` and `flamingo-17568` after those seats stopped
answering. Halloy (and any other client) therefore shows them as
present.

## Gap vs current tree

`irc_agent` stays joined until the TCP session ends or it sends QUIT.
A deaf / hung / machine-off seat that does not QUIT keeps the nick in
Ergo NAMES. Watch keep-alive / PING-only can also leave a ghost if the
socket is half-open. Systray `lastSeen stale` is a different surface
(agentic_build tray); this FR is the **IRC user list**.

## LOCKED

1. Talk-seat nicks that are actually down (no process, no PONG, box
   off) must leave `#bobiverse` (and shop / `#agentic_irc`) user lists.
2. Halloy / Ergo NAMES must match live connections, not last-seen
   ghosts.
3. Do not hide a live nick that still PINGs.
4. Do not stamp UAT from workers. Bob owns UAT.

## UNKNOWN

1. Whether flamingo sockets are half-open (no QUIT), Watch keep-alive
   only, or Ergo ghost after a silent drop.
2. Timeout (seconds) before Ergo drops a dead TCP session.
3. Whether `bob-flamingo` Watch should force-QUIT the talk-seat nicks
   when those homes have no live `irc_agent`.

## Acceptance

1. Kill or power-off both flamingo talk seats. Within a bounded time
   (LOCKED once UNKNOWN 2 is measured), `flamingo-17568` and
   `flamingo-24108` disappear from `#bobiverse` NAMES and Halloy users.
2. A live flamingo that still PINGs stays in the list.
3. No UAT stamp on the PR that implements this.

## Out of scope

- agentic_build `#175` persistent workers / control-card pool meters.
- Reinstalling Watch-BobTray on marchhare (Simon test of digest
  systray; separate).
