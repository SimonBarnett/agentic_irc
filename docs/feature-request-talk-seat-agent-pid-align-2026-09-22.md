# FR: Talk-seat nick = irc_agent PID (issue #88)

**Issue:** https://github.com/SimonBarnett/agentic_irc/issues/88

## Summary

Canonical talk-seat PID must be the Windows PID of `irc_agent.py` for that
home — never `irc_listen` PID. IRC nick `{machine}-{agentPid}` and digest
`machine:pid` must match. TSR must not imply listen PID is the seat id.

## Acceptance

- A1: Skills + docs state suffix is irc_agent PID.
- A2: Start-IrcTsr (or helper) errors if --nick suffix ≠ running agent PID.
- A3: Optional start_talk_seat starts agent with --nick {machine}-$PID.
- A4: Digest POST and IRC nick stay in sync (tests).
- A5: Future OpenProcess validation noted as out of scope (see `docs/multi-agent-one-host.md`).

Workers do not stamp ready for human UAT.