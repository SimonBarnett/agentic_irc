# Feature request: private Ergo channel `#agentic_irc` (2026-09-22)

**Repo:** SimonBarnett/agentic_irc
**Source:** Simon on `#bobiverse` 2026-09-22: FR for the IRC team to create a channel; named `/agentic_irc` → `#agentic_irc`.

## Summary

Create and document dedicated private Ergo channel `#agentic_irc` on `irc.ntsa.uk:6697` for Simon and IRC/agent talk seats (human + coordinators), separate from fleet `#bobiverse` and shop rooms `#<machine-id>`.

## LOCKED

- Channel name: `#agentic_irc`.
- Server: private Ergo `irc.ntsa.uk:6697` TLS (not Libera).
- Audience: Simon (Halloy) + talk seats / IRC team operators — not `bob-*` builder firehose.
- Do not break `#bobiverse`, shop channels, or Mode 3 pairing channels.
- Secrets stay SEAL/TOFU; no cleartext secrets on `#agentic_irc`.
- Park-only until Simon says dispatch/build. Talk seats JOIN after issue is up unless Simon says join now.

## UNKNOWN

- Autojoin policy: which nicks JOIN at Start-TalkSeat (all talk seats? coordinators only?).
- Moot mode: MODE1 floor vs MODE2 free vs no moot.
- Whether `bob-*` / Watch must stay **out** (recommended: yes).
- Persistence: Ergo chanreg / ACL / key, or open JOIN for fleet PASS holders.

## Gap vs current tree

| Today | Gap |
|---|---|
| `#bobiverse` fleet status + talk | No dedicated human/IRC-team room |
| Shop `#<machine-id>` | Per-box worker stdout, not team ops |
| `#airc-moot` Mode 3 | Pairing/elders, not general team |
| `Start-TalkSeat` `--channel` | Hardcodes fleet+shop; no `#agentic_irc` flag |
| `bob-irc` / `agentic-irc` skills | No playbook for team channel `#agentic_irc` |

## Acceptance (draft)

1. `#agentic_irc` exists on Ergo; Simon can `/join` from Halloy with connect.password.
2. Docs + skill note who JOINs, who must not (`bob-*` unless Simon says otherwise).
3. Talk-seat start path can include `#agentic_irc` without stealing homes / ghosting nicks.
4. Offline tests updated if channel-list helpers change; no CI opens IRC.

## Out of scope

- UAT stamp (Bob only).
- Changing digest/`!bobiverse` behaviour.
- Public Libera channel.
