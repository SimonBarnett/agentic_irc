# FR #322 - airc-console `#workgroup` shared lobby

## Ask

Confirm whether `#workgroup` is acceptable when Windows join is the literal
workgroup `WORKGROUP`, or whether lobby should be more specific. **No code
change until product call.**

## Product call (closed)

**Accept `#workgroup` as a shared lobby.** Documented in
`docs/airc-console-domain-lobby.md` (FR #322 section). Escape hatches:
ChanServ-register the shop, or `AIRC_CONSOLE_DOMAIN` / `--domain`.

## Non-goals

- Code special-casing the string `WORKGROUP`
- Auto `#wg-{machine}` lobbies
