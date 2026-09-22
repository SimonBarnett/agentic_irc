# Grok-talk wire envelope v1

IRC `irc_agent` enqueues listen-talk jobs; a sister worker (Grok Build / BobBridge on
`agentic_build`) consumes `grok-inbox.jsonl` and appends completions to
`grok-outbox.jsonl`. `scripts/grok_talk_drain.py` (or Watch poll) turns completions
into `outbox.txt` lines for the existing outbox poller.

Paths are under `AGENTIC_IRC_HOME` (fleet default `~\.agentic-irc-bobiverse`).

## Inbox line (`grok-inbox.jsonl`)

One JSON object per line (UTF-8).

| Field | Type | Meaning |
|-------|------|---------|
| `v` | `1` | Schema version |
| `job_id` | string | Unique id (hex) |
| `ts` | number | Unix time when enqueued |
| `asker` | string | IRC nick of human/worker |
| `channel` | string | Channel name (`#bobiverse`, shop) or PM target nick |
| `body` | string | Full PRIVMSG body (after IRC `:`) |
| `nick` | string | This seat's live/original bob-* nick |
| `machine_id` | string | Fleet id (`ionos`, `flamingo`, …) |
| `reply_target` | string | Where to PRIVMSG replies (`#bobiverse` or asker nick) |
| `body_hash` | string | Short hash for dedupe |

Example:

```json
{"v":1,"job_id":"a1b2c3d4","ts":1758470400,"asker":"simon","channel":"#bobiverse","body":"@bob-ionos status?","nick":"bob-ionos","machine_id":"ionos","reply_target":"#bobiverse","body_hash":"9f86d081"}
```

## Outbox completion (`grok-outbox.jsonl`)

| Field | Type | Meaning |
|-------|------|---------|
| `v` | `1` | Schema version |
| `job_id` | string | Matches inbox `job_id` |
| `reply_target` | string | PRIVMSG destination |
| `lines` | string[] | One English fact per line; max 350 chars each |

Example:

```json
{"v":1,"job_id":"a1b2c3d4","reply_target":"#bobiverse","lines":["@simon ionos: shop channel worker is idle.","No queued MRB on this box."]}
```

## Drain to `outbox.txt`

For each line in `lines`, append:

```
PRIVMSG <reply_target> :<text>
```

`irc_agent` sends lines that start with `PRIVMSG ` verbatim; other lines go to the
default fleet channel via `say()`.

Secrets-shaped text is dropped (`looks_like_secret`).

## Gates (IRC side)

- `grok_talk_enabled` in `grok-talk.json` or env `AGENTIC_IRC_GROK_TALK=1` (default off).
- Fuel: peer `weekly` integer **> 0**, **or** Cursor Models `remaining_pct` /
  `account_remaining_pct` / `cursor_remaining_pct` **> 0** (#70 MUST 5 / folded #68).
  `cursor_label` is display-only and is **not** fuel.
  `bobstat.write_peer` persists those three aliases when any is set (or when BOB
  POINT carries `remaining=`), and keeps prior numeric remaining across POINT
  updates that omit it. Sister `Write-BobIrcStatus` refreshes `bob-peers/<id>.json`
  with the same keys.
- Same mention eligibility as #54 (`addressed_to`, not protocol, not `bob-*` asker).
- ACK always fires when eligible; grok-talk enqueue is optional and additional.
  When `weekly=0` but Cursor remaining > 0, ACK must **not** say `cannot grok-talk`.
