# Feature request Ã¢â‚¬â€ agentic_irc extensions (2026-09-19)

Source PDF: [feature-request-moot-file-dumb-2026-09-19.pdf](./feature-request-moot-file-dumb-2026-09-19.pdf)

## Summary

Build proposal / engineering handoff for three extensions on the existing two-operator Libera TLS field kit:

1. **Moot** Ã¢â‚¬â€ multi-agent assembly (chair, roster, floor, transcript); MOOT v1 verbs; skill /agentic-moot.
2. **File sharing** Ã¢â‚¬â€ tiers S (SEAL), M (CHUNK), L (path drop); FILE v1 verbs; skill /agentic-file.
3. **Dumb connector** Ã¢â‚¬â€ non-LLM driver for ancient hosts (incl. Server 2012); DUMB v1 / CAPA v1; Python reference + .NET 4.5 irc-dumb.exe; skill /agentic-dumb.

## Constraints (from the PDF)

- Field kit, not a platform. Private Libera channel. Offline pytest only Ã¢â‚¬â€ do not open Libera from CI.
- Do not break existing AGPK/SEAL/protect/irc_agent behaviour unless the spec marks a compatible extension.
- Baseline at handoff: main @ 411a615 (current clone may be newer; treat as-is tests as regression suite).
- Implement in phase order Ã‚Â§11; phases 0Ã¢â‚¬â€œ4 are the merge floor if .NET slips.

## Status

**Ready for human UAT** (Python phases 0-4). See [mrb-2026-09-19-v2.md](./mrb-2026-09-19-v2.md). .NET Phase 5 still deferred. Phases 0â€“4 Python surface is on `main`; MRB blockers 1â€“4 (AIRC-FILE envelope, dumb listen, D2 on the wire, truncated exec spill) are implemented. See [gap-vs-feature-request-2026-09-19.md](./gap-vs-feature-request-2026-09-19.md).

| Deliverable | Status |
|---|---|
| Wire CAPA/MOOT/FILE/DUMB parsers | Implemented; W1â€“W6 covered offline |
| Moot chair/roster/floor + skill | Implemented; 3-nick non-floor SAY drop via `handle_privmsg` |
| FILE FileBag + hash-before-`complete/` | Implemented; F1â€“F8 offline including AIRC-FILE v1 envelope on tier S |
| Dumb Python jail/PSK/busy/timeout | Job runner + `dumb_agent.py` listen (connect/join/flood/CAPA/jobs); D2 no result on wire; truncated spill |
| Skills + `install_skill.py` | Present (`agentic-moot` / `agentic-file` / `agentic-dumb`) |
| `.NET` `airc-dumb.exe` | **Stub** (INFO + exit 0). MSBuild + TLS 1.2 preflight documented. `airc-dumb.cmd` wrapper added. Not a protocol clone. |
| Manual Libera session | `tests/MANUAL.md` only â€” not run by CI |

Do not claim the Server 2012 adapter exists until Phase 5 clones `dumb_agent.py`. Do not claim ready for human UAT.
