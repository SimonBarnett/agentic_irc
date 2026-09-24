---
name: jeeves-git-webhook
description: >
  Git webhooks on the ionos digest listener, announced by Jeeves only.
  Use when the user says git webhook, webhooks from git, Jeeves announce,
  GIT pull_request, GIT push, chair-outbox, issue #147, or
  /jeeves-git-webhook. Digest working_on posts stay bob-irc.
---

# Git webhooks announced by Jeeves

Issue #147. Route is live: `POST /bob/v1/git` on the same ionos listener
as the digest. Jeeves (`irc_agent.py --chair`, nick `Jeeves`) is the only
nick that says `GIT`.

Digest `POST /bob/v1/report` (change-only, `X-Bob-Secret`) stays
`bob-irc`. Do not copy that playbook here.

## Announce path

1. GitHub POSTs the event. Header `X-GitHub-Event` is required. Peer IP
   must be in `BOB_REPORT_ALLOW`. No webhook secret in git, issues, or
   channel text.
2. `enqueue_chair_fleet_privmsg` appends
   `PRIVMSG #bobiverse :GIT …` to `chair-outbox.txt` on the digest home
   (`BOB_DIGEST_HOME` = `~\.agentic-irc-bobiverse`), not `outbox.txt`
   and not `~\.agentic-irc-jeeves`.
3. Only `irc_agent.py --chair` drains `chair-outbox.txt`.
   `fleet_digest_home()` reads `BOB_DIGEST_HOME`. Without that env the
   chair uses `--home` and GIT lines stay stuck on the digest home.
   `scripts/Install-BobChair.ps1` sets `--home` / `AGENTIC_IRC_HOME` to
   `~\.agentic-irc-jeeves` and `BOB_DIGEST_HOME` to
   `~\.agentic-irc-bobiverse`. Do not share `--home` with `bob-ionos`.
4. `bob-*` and talk seats drain `outbox.txt` only. They do not read
   `chair-outbox.txt` and they do not narrate `GIT` lines.
5. A `GIT` line already sitting in `outbox.txt` from before this split can
   still be spoken once by `bob-ionos`. New events must not go there.

## Line shape

`GIT <event> <owner/repo> … by <actor>` on `#bobiverse`. Known detail:

- `ping`: zen
- `push`: branch, 12-char SHA, `N commit(s)`
- `pull_request` / `issues`: action, `#n`, title

No fleet-status spam. No `!bobiverse` from a talk seat.
