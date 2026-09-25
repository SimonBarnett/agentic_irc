# Build-and-test plan: Mode 3 DUMB exec ergonomics

**FR:** `docs/feature-request-mode3-dumb-exec-ergonomics-2026-09-19.md`  
**Issue:** https://github.com/SimonBarnett/agentic_irc/issues/2  

## Steps

1. Read `scripts/dumb_agent.py` jail/meta/timeout policy; CAPA docs.
2. Ship `docs/mode3-dumb-ops.md` covering bins, META_CHARS, `//` rule, 60s cap, put+spawn+poll cookbook (flamingo HTTPS install example).
3. Split error codes: `bin` / `meta` / `empty_argv` (or hint field) — update thin + tests.
4. Stretch if time: `download` or `spawn` op; do not weaken path jail.
5. pytest; commit/push. Slab UAT + hostile MRB.

## Success

Acceptance criteria 1–2 green; stretch optional. Issue #2 referenced in docs.
