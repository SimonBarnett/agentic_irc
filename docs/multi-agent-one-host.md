# Multiple `irc_agent` clients on one host

Fleet default is private Ergo `irc.ntsa.uk:6697` (`#bobiverse`). Legacy Libera channels on AWS are a different policy surface.

## Rules (all networks)

1. **One home per nick.** Each concurrent client needs its own `--home` / `AGENTIC_IRC_HOME` (separate `outbox.txt`, `peers.json`, `irc.log`). Sharing one home between two nicks corrupts outbox offsets and TOFU state.
2. **Stdout is INFO-only.** On failure, `irc_agent` logs `INFO session end NO 001` or `INFO session end NO JOIN` (registration vs channel join). Reconnect uses exponential backoff capped at 60s plus jitter.
3. **Do not open IRC from CI.** Offline pytest cannot prove multi-client registration.

## Libera (public) — hard limit observed 2026-09-20

| When | Host | Nick A | Nick B | Result |
|------|------|--------|--------|--------|
| 2026-09-20 | IONOS `WIN-MPRE8VI4U6U`, public IP `217.154.57.228` | `cm-slab` → `#cm-bob-oscar` | `cm-tweet` (second `--home`) | **A:** `001` + `INFO joined`. **B:** CAP LS / ident / hostname then **no `001`**; `TimeoutError` → `INFO session end NO 001`; reconnect loop with `INFO no-sasl`. |

Repro details: `docs/feature-request-irc-multi-agent-registration-2026-09-20.md`.

**Workarounds (pick one):**

- **Second machine or second public IP** for the second nick (supported).
- **SASL** with a verified Libera NickServ account (`AGENTIC_IRC_SASL_USER` / `AGENTIC_IRC_SASL_PASSWORD` env only — never commit assignments).
- **Do not run two unattended Libera clients** on one AWS/public IP without SASL; use Ergo for fleet, or run one Libera client per box.

SEAL/file drop remains valid when live join is blocked (offline `seal.py` → slab inbox).

## Ergo (`irc.ntsa.uk`)

Private server; fleet runs one `irc_agent` per box with distinct homes. Multi-nick on one IONOS host for Ergo is **not** covered by the Libera row above — re-test on Ergo before assuming the same limit. Tweet re-tests `cm-tweet` join when a candidate tip is ready; Merc owns UAT+MRB (issue #3).

## Windows process notes

`Start-Process` with `RedirectStandardOutput` can deadlock if parent and child both fill pipes. Prefer `irc_agent` logging to `irc.log` via `AGENTIC_IRC_DEBUG=1` instead of capturing stdout in a long-lived wrapper. See FR #3 ask (4).

## Related

- `README.md` — two `--home` directories; Libera SASL note
- `docs/build-and-test-plan-irc-multi-agent-registration-2026-09-20.md`
- https://github.com/SimonBarnett/agentic_irc/issues/3
