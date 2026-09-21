# docs/ index

Agents: open **live** specs below. Do not treat `mrb-*.md` / `mrb-*.pdf` as current product spec — they are hostile MRB audit history.

## Live (current)

| Doc | Role |
|---|---|
| `feature-request-bob-listen-talk-all-seats-2026-09-21.md` | Every `bob-*` ACK on @mention / Query (no grok.exe) |
| `build-and-test-plan-bob-listen-talk-all-seats-2026-09-21.md` | Worker plan for listen/talk ACK |
| `feature-request-shop-channel-worker-cc-webhook-2026-09-21.md` | Shop channels, pid workers, write-only callback, `!bobiverse` only (issue #46) |
| `build-and-test-plan-shop-channel-worker-cc-webhook-2026-09-21.md` | Worker plan for #46 |
| `feature-request-house-clean-irc-kit-2026-09-21.md` | Fleet canon alignment (issue #34) |
| `multi-agent-one-host.md` | Two `--home` dirs; Ergo vs legacy Libera |
| `beacon-v1-2026-09-19.md` | Mode 3 zero-config invite / `beacon.url` |
| `mode3-dumb-ops.md` | DUMB exec jail, operators, paths |
| `build-and-test-plan-house-clean-irc-kit-2026-09-21.md` | Worker plan for #34 |
| `tofu-rotation.md` | AGPK pin mistakes and key rotation drill |

`feature-request-report-bobiverse-digest-2026-09-21.md` (#36) is historical for the
**write** path (`!report` scrubbed). `!bobiverse` as whisper-JSON reader is kept and
redefined in the shop-channel FR.

Fleet host, channel, and nick table: **`agentic_build/docs/bobiverse.md`** and **`agentic_build/config/bobiverse.json`** (not duplicated here).

## Historical (audit only)

`mrb-*.md` and matching PDFs record past hostile MRB verdicts (mode1/2/3, invite-airc, dotnet backlog). Useful for humans tracing decisions; **not** the spec to implement from.

Older feature requests (`feature-request-*.md`) stay for traceability; prefer the dated FR that matches the open GitHub issue.
