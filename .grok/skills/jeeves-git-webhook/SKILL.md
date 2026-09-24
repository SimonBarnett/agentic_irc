---
name: jeeves-git-webhook
description: >
  Git webhooks on the ionos digest listener, announced by Jeeves only.
  Use when the user says git webhook, webhooks from git, Jeeves announce,
  GIT pull_request, GIT push, chair-outbox, issue #147, !BORED, !ACCEPT,
  !TASK, or /jeeves-git-webhook. Digest working_on posts stay bob-irc.
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
   (`~\.agentic-irc-bobiverse`), not `outbox.txt`.
3. Only `--chair` drains `chair-outbox.txt`. `bob-*` and talk seats drain
   `outbox.txt` only. They do not read `chair-outbox.txt` and they do not
   narrate `GIT` lines.
4. A `GIT` line already sitting in `outbox.txt` from before this split can
   still be spoken once by `bob-ionos`. New events must not go there.

## Line shape

`GIT <event> <owner/repo> … by <actor>` on `#bobiverse`. Known detail:

- `ping`: zen
- `push`: branch, 12-char SHA, `N commit(s)`
- `pull_request` / `issues`: action, `#n`, title

No fleet-status spam. No `!bobiverse` from a talk seat.

## Claim queue (`!BORED` / `!ACCEPT`)

Jeeves is if-then only. No model call and no ranking. `bob-*` does **not**
auto-claim when it sees `GIT`.

Claimable webhook events are appended to the unaccepted list in the same
step that queues the `GIT` line (`apply_git_webhook`). Ping and other
noise are announced and **not** queued.

Allowlist (anything else is skipped, including `ping`, `push`, `closed`,
`edited`, `synchronize`, `labeled`):

| GitHub event | action | `{task}` |
|---|---|---|
| `issues` | `opened` | `PR` |
| `pull_request` | `opened` | `MRB` |
| `pull_request` | `ready_for_review` | `MRB` |

`PR` is the issue→implement name. `BUILD` is not used.

Digest home (`~\.agentic-irc-bobiverse`, the chair home):

- `git-unaccepted.json` — FIFO by `seq`. Fields: `repo` (`owner/repo`),
  `task`, `id` (`#n`), `ts`, `line` (the `GIT` text), `event`, `action`.
- `git-accepted.jsonl` — one stamp per accept (`repo`, `task`, `id`,
  `nick`, `channel`, `ts`). A GitHub redelivery of an accepted triple
  does not re-queue it.
- `git-worker-activity.json` — last shop activity time per `w-*` nick.

Jeeves already JOINs every shop, so it hears `!BORED` itself. No `bob-*`
relay.

Worker, on **its** shop (`#flamingo`, `#ionos`, `#marchhare`,
`#ce-priority-dev1`):

1. Do not send `!BORED` until this worker has had no job for more than
   120 seconds. That wait is the worker's clock.
2. Send exactly `!BORED`.
3. Jeeves offers the oldest unaccepted row on that shop:
   `!TASK {repo} {task} {id}`. Offering does not remove the row.
4. Reply on that shop: `!ACCEPT {repo} {task} {id}`.
5. Jeeves deletes the row, appends the stamp, and replies
   `OK !ACCEPT {repo} {task} {id}`.
6. A second `!ACCEPT` for the same triple does not write again. Reply
   `NAK !ACCEPT {repo} {task} {id}`.

Chair gate for `!BORED` (fixed order):

- Not a `w-*` nick, or not that worker's shop → silence.
- Activity timestamp newer than 120 seconds → `NAK !BORED wait`
  (timestamp unchanged, so a retry is not pushed back forever).
- Digest `working_on` for that worker pid is non-empty →
  `NAK !BORED busy`.
- Queue empty → `NAK !BORED empty`.
- Otherwise `!TASK …`.

Shop chatter (any shop PRIVMSG from that `w-*` other than `!BORED` /
`!ACCEPT`) sets the activity timestamp. A `!BORED` that gets `!TASK`,
`busy`, or `empty` sets it too. A successful `!ACCEPT` from that worker
sets it too. If Jeeves has never seen the nick and `working_on` is
empty, the first `!BORED` is offered — the worker must already have
waited 120 seconds; Jeeves cannot see a silent worker's clock.

`bob-*` may send `!ACCEPT {repo} {task} {id}` on `#bobiverse` or its own
shop (optional fast path). Same stamp, same NAK on a repeat. `bob-*`
does not send `!BORED`.

`FILE v1 ACCEPT` is file transfer. It is not this command.

Offers, `OK`, and `NAK` are normal `PRIVMSG` from Jeeves on the channel
the command arrived on. They are not written to `chair-outbox.txt`.
Do not re-announce `GIT` from `bob-*`.

After PASS-nits merge to `main`, ionos must recycle Jeeves and the
digest listener (`!recycle ionos` pulls `agentic_irc`, restarts the
chair, restarts `bobcallback`). Until that recycle, new events are not
queued and shop `!BORED` gets no answer. Also recycle `bob-*`
Watch-Bobiverse so each ear runs the merged tree; those ears do not
emit `!ACCEPT` on their own.
