# Gap vs feature-request PDF (2026-09-19)

**Spec:** [feature-request-moot-file-dumb-2026-09-19.pdf](./feature-request-moot-file-dumb-2026-09-19.pdf)  
**First-audit HEAD:** `1a11e98`  
**This pass:** strengthen §12 offline tests + small FILE/dumb holes those tests need.  
**Method:** PDF §12 tables + Appendix C vs what offline tests assert. No Libera.

## Snapshot

| Area | Code | Tests vs §12 |
|---|---|---|
| Wire parsers | Yes | W1–W6 covered |
| Moot | Yes | M1–M7; 3-nick floor via `handle_privmsg` |
| File | Receive path now hashes on DONE; ABORT + disk-cap | F1–F8 offline (F1 is hash-into-`complete/`, not AIRC-FILE envelope) |
| Dumb Python | Job runner + jail/meta/timeout/prefix | D1–D10 offline except D2 “no result on the wire” |
| Skills + installer | Yes | Not asserted in pytest |
| `.NET` | **Stub** (INFO + exit 0) + `airc-dumb.cmd` | Skip unless `DOTNET_DUMB_EXE` |
| CI | `pytest -q` only | Tests must not mention `irc.libera.chat` |

`pytest -q` this pass: **68 passed, 2 skipped** (`test_chmod_failure_raises` Unix-only; `test_dotnet_exe_if_present` unless `DOTNET_DUMB_EXE`).

---

## §12.1 Wire (Table 9)

| ID | Expect | Status |
|---|---|---|
| W1 | Each Table 3 verb parses | **Covered** (`test_w1_each_table3_verb`) |
| W2 | lowercase / missing v1 / extra tokens → None | **Covered** (incl. OPEN extra tokens) |
| W3 | FILE OFFER path-like name | **Covered** |
| W4 | DUMB `n=100` → None | **Covered** |
| W5 | CAPA missing `verbs=` | **Covered** |
| W6 | SEAL v2 only via `seal.parse_seal_line` | **Covered** |

## §12.2 Moot (Table 10)

| ID | Expect | Status |
|---|---|---|
| M1 | OPEN + JOIN×2 + ROSTER → roster 3 | **Covered** |
| M2 | non-floor SAY dropped | **Covered** (3-nick + `handle_privmsg`) |
| M3 | FLOOR / SAY / YIELD `*` / CLOSE; further SAY dropped | **Covered** |
| M4 | HANDOFF off-roster | **Covered** |
| M5 | PART by floor holder → floor none | **Covered** |
| M6 | two OPEN same id → first wins | **Covered** |
| M7 | seq not increasing | **Covered** |

## §12.3 File (Table 11)

| ID | Expect | Status |
|---|---|---|
| F1 | Tier S 1 KiB → `complete/` sha256 match | **Partial.** 1 KiB matching hash writes `complete/` (incl. DONE path). Offer still seals **raw bytes**, not AIRC-FILE v1 envelope (§5.2). |
| F2 | Tier M 20 KiB shuffled | **Covered** |
| F3 | Hash mismatch DONE → no `complete/` | **Covered** via `handle_file` |
| F4 | offer `identity.json` | **Covered** |
| F5 | slash/space name | **Covered** |
| F6 | second OFFER same id ignored | **Covered** |
| F7 | ABORT mid-bag | **Covered** |
| F8 | disk cap → ACCEPT not sent / refuse | **Covered** (`FILES_HOME_CAP` monkeypatch) |

## §12.4 Dumb (Table 12)

| ID | Expect | Status |
|---|---|---|
| D1 | PSK ping ok | **Covered** |
| D2 | unknown operator | **Partial.** `error=operator` in-process. PDF also says no result **on the wire**; `handle_dumb` still only INFO-logs (no job runner on the IRC client). |
| D3 | jail escape | **Covered** (`agent-drop\..\Windows\win.ini`, UNC, secret names) |
| D4 | put then get sha256 | **Covered** (asserts `hashlib.sha256(data)`) |
| D5 | exec timeout | **Covered** (`subprocess.TimeoutExpired` monkeypatch) |
| D6 | busy | **Covered** |
| D7 | argv[0] not allowed | **Covered** (split from D5) |
| D8 | meta without `--allow-meta` | **Covered** |
| D9 | prefix ≠ `from_nick` | **Covered** (`handle_dumb` drops) |
| D10 | wrong PSK | **Covered** (`pytest.raises`) |

---

## Appendix C

| # | Criterion | Status |
|---|---|---|
| 1 | pytest -q green + §12 tests | Green; F1 envelope + D2-on-wire still thin |
| 2 | Three skills + installer + safety rules | Present; not pytest-covered |
| 3 | 3-party in-process moot to CLOSE | **Covered** via `handle_privmsg` |
| 4 | 20 KiB tier M + sha256 | **Covered** |
| 5 | Jail + unknown operators | **Covered** |
| 6 | DUMB-PSK Python seal/open | **Covered** |
| 7 | .NET + MSBuild + TLS 1.2 preflight | **Stub only.** Recipe + `airc-dumb.cmd` + skill note. Not a protocol clone. |
| 8 | README field kit | Yes; .NET described as stub |
| 9 | No CI resolves `irc.libera.chat` | Workflow is pytest only; tests forbid the hostname |

---

## Remaining PDF items (honest)

Do **not** treat this list as ready for human UAT.

1. **Phase 5 .NET protocol clone** — `Program.cs` still prints INFO and exits 0. No TcpClient, SslStream, AES-GCM, jail, CAPA. Highest remaining host-constraint gap.
2. **`dumb_agent.py` listen loop** — `main` is `INFO no-listen`. PDF wants a connect loop in the spirit of `irc_agent`. Modern operators use `irc_agent` + `dumb_ctl` / in-process runner.
3. **Tier S AIRC-FILE envelope** (§5.2) — `offer --tier S` still seals raw file bytes, not `AIRC-FILE v1` headers.
4. **Truncated exec spill** — JSON truncates at 8 KiB; PDF also wants `dumb/results/<id>.txt`.
5. **D2 on the wire** — unknown operator returns an in-process error dict; the IRC client does not run jobs or emit a result box.
6. **`FLOOR_IDLE_S`** — skill-only (PDF: optional chair hint in v1).
7. **`YIELD *`** — code sets `floor=None` (state-machine box). Table 3 prose says “* returns it to chair”. Left as-is.
8. **Manual Libera session** (`tests/MANUAL.md` / §12.6) — human-only; not run from this machine.
9. **install_skill / skill text** — not locked by pytest.

## Non-goals (Appendix B) — correctly absent

Group SEAL, DCC, web UI, signed `airc-dumb.exe` from CI, connector as SYSTEM with no jail.

## This dispatch

Gap doc committed first. Offline tests moved toward §12 (file hash/jail, moot non-floor, dumb jail/timeout/meta/prefix). `pytest -q` green. .NET documented as stub. **Not** self-declared ready for human UAT.
