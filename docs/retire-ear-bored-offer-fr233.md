# FR #233: Retire bob-* ear `!bored` OFFER path

## Why

gh-Jeeves #106 (CAST IRON): **Jeeves** assigns the next job when a worker
sends `!bored` in `#{machine}`. An ear that also OFFERs races Jeeves.

## Change

`irc_agent` bob-* ears (`fleet_bob`, not `--chair`) treat `!bored` as a
**no-op**: log `git-claim bored ear-noop` and do not call `offer_top` or
write ASSIGN. ACK/DONE and other shop duties remain.

## Tests

`tests/test_git_claim.py::test_bob_ear_bored_is_noop_jeeves_assigns`
