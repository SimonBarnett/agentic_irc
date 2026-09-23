---
name: jeeves-git-webhook
description: >
  Git webhooks on the ionos digest listener, announced by Jeeves only.
  Use when the user says git webhook, webhooks from git, Jeeves announce,
  extend the webhook, issue #147, or /jeeves-git-webhook. Digest
  working_on posts stay bob-irc. Do not implement until Simon says go.
---

# Git webhooks announced by Jeeves

Parked: https://github.com/SimonBarnett/agentic_irc/issues/147
and `docs/feature-request-git-webhook-jeeves-announce-2026-09-23.md`.
Simon `#bobiverse` 2026-09-23. Park-only until Simon says go. Do not
dispatch. No UAT stamp.

Digest `POST /bob/v1/report` (change-only, `X-Bob-Secret`) stays
`bob-irc`. Do not copy that playbook here.

## LOCKED

1. Repo is `agentic_irc`. Same ionos listener as the digest webhook.
   Do not invent a second public host. A sibling path on that listener
   is allowed. `POST /bob/v1/report` behaviour for bob peers stays.
2. Accept git (GitHub) webhook POSTs. Jeeves (`irc_agent.py --chair`,
   nick `Jeeves`) is the only nick that announces an accepted event.
   `bob-*` and talk seats do not narrate them. Talk seats never send
   `!bobiverse`.
3. No webhook secret, HMAC, or token in git, issues, or channel text.
4. No fleet-status spam. This announce is the git event only.

## UNKNOWN

- Which GitHub events (push, pull_request, issues, ping, others).
- Announce room (`#bobiverse`, shop, or whisper).
- Reuse `X-Bob-Secret` or a separate GitHub HMAC. Do not invent the
  header or the secret path.
- Which payload fields Jeeves prints (repo, SHA, actor, title).
- IP allow-list versus GitHub hook source ranges.

## When Simon says go

- A1: a git webhook POST is accepted on the documented route.
- A2: Jeeves announces that event. No fleet-status spam.
- A3: digest `POST /bob/v1/report` is unchanged.
- A4: no secrets in the repo. Tests cover the route with no live GitHub.
- Workers do not stamp UAT.
