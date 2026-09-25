# FR: reply on the same call channel (bobs + workers)

## Summary
Simon (agentic_irc #187): bobs and workers MUST listen on call channels they are in and reply to the same channel.

## Gap
`irc_agent.say()` and bare outbox lines (no `PRIVMSG` prefix) always send to `self.chan` (first JOIN = usually `#bobiverse`). Inbound mentions on shop / extras already use the PRIVMSG target for ACK, but agent/outbox replies without an explicit channel land on fleet.

## Acceptance
| ID | Criterion |
|----|-----------|
| A1 | Channel PRIVMSG handled while joined to that channel (existing `_joined_channel`). |
| A2 | Bare outbox lines (no `PRIVMSG ` prefix) send to the **last inbound joined channel** when set; else `self.chan`. |
| A3 | Explicit `PRIVMSG #chan :…` outbox lines unchanged. |
| A4 | Mention ACK still uses inbound `target` when `to_channel`. |
| A5 | Tests cover sticky reply channel + `reply_target_for`. |
