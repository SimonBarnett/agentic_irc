# Feature request: private Ergo channel for Simon + IRC team (2026-09-22)

**Repo:** SimonBarnett/agentic_irc
**Source:** Simon on `#bobiverse` 2026-09-22: "feature request for the irc team, create a channel for us#" then "irc team*".

## Summary

Create and document a **dedicated private Ergo channel** on `irc.ntsa.uk:6697` for Simon and the IRC/agent talk seats (human + coordinators), separate from fleet `#bobiverse` (MODE2 status) and shop rooms `#<machine-id>`.

## LOCKED

- Server: private Ergo `irc.ntsa.uk:6697` TLS (not Libera).
- Audience: Simon (Halloy) + talk seats / IRC team operators — not `bob-*` builder firehose.
- Do not break `#bobiverse`, shop channels, or Mode 3 pairing channels.
- Secrets stay SEAL/TOFU; no cleartext secrets on the new channel.
- Park-only until Simon names the channel and says dispatch/build.

## UNKNOWN

- Exact channel name (Simon typed `us#` — incomplete). Candidates to confirm: `#us`, `#ops`, `#irc-team`, other.
- Autojoin policy: which nicks JOIN at Start-TalkSeat (all talk seats? coordinators only? Simon invite?).
- Moot mode: MODE1 floor vs MODE2 free vs no moot.
- Whether `bob-*` / Watch must stay **out** (recommended: yes).
- Persistence: Ergo chanreg / ACL / key, or open JOIN for fleet PASS holders.

## Gap vs current tree

| Today | Gap |
|---|---|
| `#bobiverse` fleet status + talk | No dedicated human/IRC-team room |
| Shop `#<machine-id>` | Per-box worker stdout, not team ops |
| `#airc-moot` Mode 3 | Pairing/elders, not general team |
| `Start-TalkSeat` `--channel` | Hardcodes fleet+shop; no team channel flag |
| `bob-irc` / `agentic-irc` skills | No playbook for creating/registering a team channel |

## Acceptance (draft)

1. Channel exists on Ergo; Simon can `/join` from Halloy with connect.password.
2. Docs + skill note the name, who JOINs, who must not JOIN (`bob-*` unless Simon says otherwise).
3. Talk-seat start path can include the channel without stealing homes / ghosting nicks.
4. Offline tests updated if channel list helpers change; no CI opens IRC.

## Out of scope

- UAT stamp (Bob only).
- Changing digest/`!bobiverse` behaviour.
- Public Libera channel.
