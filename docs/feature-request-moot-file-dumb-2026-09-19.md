# Feature request â€” agentic_irc extensions (2026-09-19)

Source PDF: [feature-request-moot-file-dumb-2026-09-19.pdf](./feature-request-moot-file-dumb-2026-09-19.pdf)

## Summary

Build proposal / engineering handoff for three extensions on the existing two-operator Libera TLS field kit:

1. **Moot** â€” multi-agent assembly (chair, roster, floor, transcript); MOOT v1 verbs; skill /agentic-moot.
2. **File sharing** â€” tiers S (SEAL), M (CHUNK), L (path drop); FILE v1 verbs; skill /agentic-file.
3. **Dumb connector** â€” non-LLM driver for ancient hosts (incl. Server 2012); DUMB v1 / CAPA v1; Python reference + .NET 4.5 irc-dumb.exe; skill /agentic-dumb.

## Constraints (from the PDF)

- Field kit, not a platform. Private Libera channel. Offline pytest only â€” do not open Libera from CI.
- Do not break existing AGPK/SEAL/protect/irc_agent behaviour unless the spec marks a compatible extension.
- Baseline at handoff: main @ 411a615 (current clone may be newer; treat as-is tests as regression suite).
- Implement in phase order Â§11; phases 0â€“4 are the merge floor if .NET slips.

## Status

Implementation largely present on `main` @ e55f501 (scripts + skills + offline tests; `pytest` 52 pass / 1 skip on IONOS 2026-09-19). `src/dumb_dotnet` is still a stub. See `docs/build-and-test-plan.md` — Bob dispatched gap-close / harden on **ionos**.
