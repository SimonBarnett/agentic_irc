# FR #230: sender account verification + irc_listen --from-account

**Issue:** https://github.com/SimonBarnett/agentic_irc/issues/230

## Behaviour
- `irc_agent` CAP REQ includes `account-notify`, `extended-join`, `account-tag` with `sasl` (server ACKs what it supports).
- Nick→account map in `$home/accounts.json` from ACCOUNT / extended-join / account-tag / NICK / QUIT.
- Raw tagged lines still go to `irc.log` when `AGENTIC_IRC_DEBUG=1`.
- `irc_listen --from-account <acct>` (repeatable) drops lines without that logged-in account.
- Default fleet listen behaviour unchanged (no filter unless flag set).
- Opt-in `--include-account` adds `account=` to FROM lines.

## Tests
`tests/test_account_map_fr230.py`
