# Gap vs feature-request PDF (2026-09-19)

**Spec:** [feature-request-moot-file-dumb-2026-09-19.pdf](./feature-request-moot-file-dumb-2026-09-19.pdf)  
**Audit HEAD:** `1a11e98` (tree already contains moot/file/dumb Python; do not treat as greenfield)  
**Method:** PDF §12 tables + Appendix C vs what offline tests actually assert. No Libera.

## Snapshot

| Area | Code present? | Tests prove PDF case? |
|---|---|---|
| Wire parsers (`scripts/wire.py`) | Yes | Partial (W2–W6 yes; W1 not every Table 3 verb) |
| Moot state (`scripts/moot.py` + `Client.handle_moot`) | Yes | M1–M7 exist but drive `apply_moot` directly, not `handle_privmsg` |
| File (`scripts/filexfer.py` + `handle_file`) | Partial | F3–F5 thin; F1/F2 undersized; F6–F8 absent |
| Dumb Python (`scripts/dumb_agent.py`) | Partial (job runner, no listen loop) | D1–D4/D6/D7/D10 yes; D3/D5/D8/D9 thin or missing |
| Skills + `install_skill.py` | Yes (four skills, `--list`) | Not asserted in pytest |
| `.NET` `src/dumb_dotnet` | **Stub** (INFO + exit 0) | No `DOTNET_DUMB_EXE` skip-test yet |
| README field-kit voice | Yes | — |
| CI no Libera | `.github/workflows/test.yml` is `pytest -q` only | Tests do not open sockets to `irc.libera.chat` |

Baseline recorded on IONOS: `pytest -q` → **52 passed, 1 skipped** (`test_chmod_failure_raises` is Unix-only).

---

## §12.1 Wire (Table 9)

| ID | PDF expect | Proven today | Gap |
|---|---|---|---|
| W1 | Each Table 3 verb, canonical spacing → parse success | OPEN + JOIN only | Missing PART, HANDOFF, FLOOR, SAY, POINT, YIELD, ROLL, ROSTER, CLOSE |
| W2 | lowercase verb / missing v1 / extra tokens → None | lowercase + missing v1 | extra tokens not specifically asserted |
| W3 | FILE OFFER path-like `./x` → None | Yes (`test_file_offer_pathlike_name`, `test_pathlike_name_rejected`) | — |
| W4 | DUMB `n=100` → None (MAX_N 64) | Yes | — |
| W5 | CAPA missing `verbs=` → None | Yes | — |
| W6 | SEAL v2 only via `seal.parse_seal_line` | Yes | — |

## §12.2 Moot (Table 10)

PDF: drive via `Client.handle_privmsg` with fake prefixes. Current tests call `moot.apply_moot`.

| ID | PDF expect | Proven today | Gap |
|---|---|---|---|
| M1 | OPEN + JOIN×2 + ROSTER → roster 3, open | OPEN+JOIN×2 (no ROSTER line) | ROSTER not applied; not via `handle_privmsg` |
| M2 | non-floor SAY in mode=floor dropped | Yes, thin (`test_say_from_non_floor_dropped`) | 3-nick listener never held floor not shown end-to-end |
| M3 | FLOOR, SAY, YIELD `*`, chair CLOSE; further SAY dropped | Yes | — |
| M4 | HANDOFF off-roster → chair unchanged | Yes | — |
| M5 | PART by floor holder → floor none | Yes | — |
| M6 | two OPEN same id, different chairs → first wins | Yes | — |
| M7 | seq not increasing → SAY dropped | Yes | — |

Phase 2 exit: “simulated 3-nick moot reaches CLOSE; listener that never held the floor emitted zero SAY lines” — **not fully proven** (no 3-nick transcript walk through `handle_privmsg`).

## §12.3 File (Table 11)

`complete_write` hash-checks before write. `FileBag` reassembles shuffled chunks. `handle_file` **INFO-logs OFFER and feeds CHUNK into FileBag**; it does **not** call `complete_write` on DONE, does not track duplicate OFFER, does not ABORT bags, does not enforce `FILES_HOME_CAP`.

Tier S `offer()` seals **raw file bytes**, not the AIRC-FILE v1 envelope in PDF §5.2.

| ID | PDF expect | Proven today | Gap |
|---|---|---|---|
| F1 | Tier S 1 KiB → `complete/` sha256 match | No | No 1 KiB SEAL/AIRC-FILE path into `complete/` |
| F2 | Tier M 20 KiB shuffled | 200 random bytes shuffled | Size is ~1/100 of spec |
| F3 | Hash mismatch DONE → no `complete/` write | `complete_write` with bad hash | Not via FILE DONE / `handle_file` |
| F4 | offer `identity.json` → nonzero exit | Yes | — |
| F5 | name slash or space rejected | Yes | — |
| F6 | second OFFER same id ignored | No | No offer registry |
| F7 | ABORT mid-bag → no complete; bag gone | No | `FileBag` has no abort |
| F8 | disk cap exceeded → ACCEPT not sent / refuse | No | `FILES_HOME_CAP` constant unused |

## §12.4 Dumb (Table 12)

Job runner exists (jail, operator list, busy lock, bin allowlist, PSK helpers). `dumb_agent.main` prints `INFO no-listen` — **no TLS/IRC loop**. Tests call `handle_dumb_payload` in-process.

| ID | PDF expect | Proven today | Gap |
|---|---|---|---|
| D1 | PSK roundtrip ping → ok | Yes | — |
| D2 | `from_nick` not in `--operators` | Yes (`error=operator`) | PDF also says no result **on the wire**; no wire assertion |
| D3 | get `C:\agent-drop\..\Windows\win.ini` → `error=jail` | Analog path via `tmp_path/../Windows/win.ini` | No UNC / drive-letter / `identity.json` put cases |
| D4 | put then get same bytes | Bytes match; `sha256 == sha256` is tautological | Should assert against `hashlib.sha256(data)` |
| D5 | exec timeout → `error=timeout`; child killed | **Not proven** — test is named timeout but asserts `error=bin` for `not-a-bin.exe` | Need monkeypatched runner / `TimeoutExpired` |
| D6 | second exec while first runs → busy | Yes | — |
| D7 | argv[0] not allowed → `error=bin` | Yes (same test as D5) | Split from timeout |
| D8 | meta `&\|><^` without `--allow-meta` | No | Runner does not reject those tokens |
| D9 | prefix ≠ `from_nick` → drop | No | `handle_dumb` does not compare IRC prefix to DUMB `from_nick` |
| D10 | wrong PSK → decrypt fail, no exec | Yes (bare `except`) | Prefer `pytest.raises` |

## Appendix C (acceptance one-pager)

| # | Criterion | Status |
|---|---|---|
| 1 | pytest -q green + §12 tests | Green count; §12 incomplete (this doc) |
| 2 | Three skills + install_skill + hard safety rules | Present in tree; not pytest-covered |
| 3 | 3-party in-process moot to CLOSE with floor | State machine yes; not 3-nick via `handle_privmsg` |
| 4 | 20 KiB tier M + sha256 | Only 200-byte bag |
| 5 | Fake connector refuses jail + unknown operators | Yes (thin jail) |
| 6 | DUMB-PSK Python seal/open same blob | Yes (D1) |
| 7 | .NET project + documented MSBuild + TLS 1.2 preflight | **Stub exe**; README/skill mention MSBuild + SchUseStrongCrypto. Not a protocol clone. No `airc-dumb.cmd` wrapper |
| 8 | README field kit, private channel | Yes |
| 9 | No CI job resolves `irc.libera.chat` | Workflow is pytest only; no test opens Libera |

## Implementation gaps (not just tests)

These are PDF MUST items the Python tree does not fully do:

1. **`.NET` Phase 5** — `Program.cs` prints two INFO lines and returns 0. No TcpClient, SslStream, AES-GCM, jail, or CAPA. Honest remaining work; do not claim the Server 2012 adapter exists.
2. **`dumb_agent.py` listen loop** — PDF wants a connect loop in the spirit of `irc_agent`. Current `main` is a no-listen stub. Operators on modern Python are expected to use `irc_agent` + `dumb_ctl` / in-process runner.
3. **FILE receive path** — DONE does not hash-check into `files/complete/`; ABORT/disk-cap/duplicate-OFFER missing.
4. **Tier S AIRC-FILE envelope** (§5.2) — offer seals raw bytes, not `AIRC-FILE v1` headers.
5. **Truncated exec** — 8 KiB cap truncates the JSON; PDF also wants `dumb/results/<id>.txt`. Not written.
6. **`FLOOR_IDLE_S`** — skill-only; no chair timer in code (PDF: optional chair hint in v1).
7. **`YIELD *`** — code sets `floor=None` (matches the state-machine box “chair may grant”). Table 3 prose says “* returns it to chair”. Left as-is; not a new API.

## Non-goals (Appendix B) — correctly absent

Group SEAL, DCC, web UI, signed `airc-dumb.exe` from CI, connector as SYSTEM with no jail.

## This dispatch’s intended close (not UAT)

Strengthen the thinnest offline tests toward §12 (file hash/jail, moot non-floor, dumb jail/timeout/meta/prefix) without opening Libera. Fill only the small FILE/dumb holes those tests need (hash-before-write already exists). Document the .NET stub honestly. Do not self-declare ready for human UAT.
