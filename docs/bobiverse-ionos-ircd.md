# Ionos Ergo — `#ionos` shop channel

**Issue:** https://github.com/SimonBarnett/agentic_irc/issues/70  
**Sister cross-link:** add one row to `agentic_build/docs/bobiverse.md` shop table:
`ionos` → `#ionos`, builder `bob-ionos`, workers `w-io-<pid>` (no UAT stamp here).

## Operator facts

- Private Ergo on ionos: TLS `irc.ntsa.uk:6697` only (not Libera).
- Fleet room `#bobiverse` and shop `#ionos` must both accept registered fleet nicks.
- **`bob-ionos`** JOINs **`#bobiverse`** and **`#ionos`** on every connect/reconnect
  (Watch-Bobiverse → `scripts/irc_agent.py` sends one `JOIN` per channel).
- Git workers on ionos: nick `w-io-<pid>`, home
  `~\.agentic-irc-bobiverse\workers\ionos\<pid>`, shop **`#ionos` only**.

## Verify after Watch recycle

In `~\.agentic-irc-bobiverse\irc.log` (with `AGENTIC_IRC_DEBUG=1`) or Ergo logs,
same session should show:

```
JOIN #bobiverse
JOIN #ionos
```

(and matching JOIN echoes for `bob-ionos`).

## Service recovery

Windows service **`BobIrcd`** (`Start-Service BobIrcd`). Do not use the removed
`BobIrcd-ionos` scheduled task. See skill `bob-irc`.

## Jeeves (digest chair)

Nick `Jeeves`, `irc_agent.py --chair`.

| | Path |
|---|---|
| `--home` / `AGENTIC_IRC_HOME` | `~\.agentic-irc-jeeves` |
| `BOB_DIGEST_HOME` (`digest.json`, `chair-outbox.txt`) | `~\.agentic-irc-bobiverse` |

`scripts/Install-BobChair.ps1` sets both and stops a prior `--chair` / nick
`Jeeves` before start. Do not share `--home` with `bob-ionos`.

BobIrcd NSSM and the hook that starts Jeeves when the IRC server starts live
in **agentic_build** (`chairNick` `Jeeves`). This repo does not define that
service.
