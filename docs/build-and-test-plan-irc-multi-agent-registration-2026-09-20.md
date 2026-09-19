# Build-and-test plan: multi-agent irc_agent registration (no 001)

**FR:** `docs/feature-request-irc-multi-agent-registration-2026-09-20.md`

## Steps

1. Read `scripts/irc_agent.py` CAP/NICK/USER/001/JOIN timeout path; compare with working `cm-slab` session logs on IONOS.
2. Reproduce or document: second nick same public IP → no 001.
3. Improve TimeoutError INFO (NO 001 vs NO JOIN); add reconnect backoff.
4. Document multi-agent-on-one-box Libera limits / workarounds in README or `docs/multi-agent-one-host.md`.
5. Check Windows stdout redirect / Start-Process deadlock notes.
6. pytest + manual notes; commit/push. Tweet UAT+MRB.

## Success

FR acceptance green; Tweet can join as cm-tweet alongside cm-slab or has a documented path.
