# airc console (FR #253)

Installable Windows service: IRC nick **`console-<machinename>`** on **`#{machinename}`**
(issue #286 — bare `console` is not unique on shared Ergo).

## Behaviour

- Registers / identifies the console nick (NickServ GUID in `console.password`)
- JOINs `#{machinename}` (creates channel when the network allows); **silent** in channel
- Direct PRIVMSG from authenticated operators opens a per-user shell session
- PRIVMSG text is piped to that console; stdout returns in Query (never on the shop channel)
- Empty operators/accounts refused

## Install (Windows)

### Preferred: single MSI (issue #305)

Download `airc-console-<ver>.msi` and run it. The MSI is **per-machine** (UAC),
installs to `C:\ai\airc-console`, then runs `Install-AircConsole.cmd` elevated
(seeds `ergo.password`, mints NickServ GUID, registers NSSM `AircConsole`, starts it).

```bat
msiexec /i airc-console-0.1.16.msi
```

### From scripts (also UAC self-elevates)

Downloaded packages are **unsigned**. Do **not** double-click / invoke the `.ps1`
directly under Restricted/AllSigned — that fails with "not digitally signed"
(FR #256). Use the `.cmd` wrapper (Unblock-File + `-ExecutionPolicy Bypass`).
`Install-AircConsole.ps1` requests UAC when not already admin (issue #305).

NSSM **Application** is `powershell.exe`; Arguments are
`-NoProfile -ExecutionPolicy Bypass -File …\Start-AircConsole.ps1 -ServiceMode …`.

The release includes **`third_party/nssm/win64/nssm.exe`** (issue #266).

```bat
REM UAC prompt if needed — unattended (#277): seeds secrets + starts service
scripts\Install-AircConsole.cmd
```

Install copies **release** `config\ergo.password` →
`%\USERPROFILE%\.airc-console\ergo.password` (issue #294 — clients need no
`\.grok`), mints NickServ GUID `console.password` if missing, resolves absolute
`python.exe` into NSSM `-Python` (LocalSystem has no PATH — issue #282), removes
any prior service, installs, and **starts** `AircConsole` (Running). Pass
`-NoStart` only to skip start.

Foreground smoke:

```bat
scripts\Start-AircConsole.cmd -SelfTest
scripts\Start-AircConsole.cmd -Operators Simon
```

## Release

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\Pack-AircConsoleRelease.ps1
# -> dist/airc-console-<ver>.msi (+ .sha256)
```

GitHub Actions workflow `airc-console-release.yml` publishes tag `airc-console` (rolling) and immutable `airc-console-v*`.
