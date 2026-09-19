# Mode 3 GitHub Release (U6)

**Default (locked unless Simon overrides):** immutable version tags **plus** one rolling tag whose assets are replaced.

| Kind | Tag | Mutability |
|---|---|---|
| Rolling | `mode3-thin` | **Replace assets** on each green build of `src/moot_thin/**` on `main` (and `workflow_dispatch`) |
| Version | `airc-moot-thin-vX.Y.Z` | **Immutable.** Created when `src/moot_thin/VERSION` is a tag that does not yet exist |

`X.Y.Z` is the single line in `src/moot_thin/VERSION` (no `v` prefix in the file).

## Artefacts on both release kinds

- `airc-moot-thin.exe` — 32-bit Win32 ANSI console PE
- `airc-moot-thin.exe.sha256` — `Get-FileHash` SHA-256, two-space `hash  filename` line
- `airc-moot-thin.ini.example` — companion config; **no secrets**

Do not attach `connector.key`, PSK material, SASL passwords, or API key assignments.

## Workflow

`.github/workflows/mode3-thin-release.yml`

- Builder: `windows-latest`, MSVC **x86** (`ilammy/msvc-dev-cmd` `arch: x86`).
- Runs `src/moot_thin/build.bat`, then `airc-moot-thin.exe --selftest`.
- Does **not** open Libera.
- `permissions.contents: write` so `GITHUB_TOKEN` can publish.
- Rolling release uses tag `mode3-thin` and `target_commitish` of the commit that built it.
- Version release is created only if `airc-moot-thin-v$(VERSION)` is absent.

`latest` as a GitHub Release flag is **not** used (other repo artefacts must not be displaced). Operators who want "whatever is current" download tag `mode3-thin`. Operators who want a pin download `airc-moot-thin-vX.Y.Z`.

## Version bump

1. Edit `src/moot_thin/VERSION` and the matching `#define AIRC_THIN_VERSION` in `main.c` (pytest checks they match).
2. Push to `main`. Rolling tag updates. A new immutable tag is created.

Rebuilding the same `VERSION` only refreshes `mode3-thin`. It does not rewrite the immutable tag.

## Checksum verify (operator)

```bat
certutil -hashfile airc-moot-thin.exe SHA256
type airc-moot-thin.exe.sha256
```

## Secrets

PSK / connector key is generated **off IRC** (`python scripts/seal.py dumb-key --home ...` on a box that already runs Mode 2, or a raw 32-byte file). Fingerprint is SHA-256 of the 32-byte key; compare out of band. The exe must never print the key. This file must never contain `password=` assignments.
