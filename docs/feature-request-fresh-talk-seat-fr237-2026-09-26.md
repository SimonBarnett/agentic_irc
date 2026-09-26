# FR #237: Start-TalkSeat.ps1 fails on a fresh home

## Problem

The first bind/start path used `$expectedNick` before it was set, and could launch `irc_agent` with an empty `--nick`. A second path called undefined `Start-TalkAgent`.

## Fix

- Fresh / restart start: `Start-OneSeatAgent -NickToStart "$mid-0" -AutoNick` so the agent rewrites to `{machine}-{own PID}`.
- Never pass an empty nick; refuse empty in `Start-OneSeatAgent`.
- Reuse path: compute `$expectedNick` from the live agent PID before `Assert-HomeBind`.
- Listen-without-agent: bind-check with `$mid-0` so a foreign-owned home is still refused.

## Tests

`tests/test_talk_seat_fresh_home_fr237.py`
