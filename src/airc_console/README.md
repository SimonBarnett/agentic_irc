# airc console (FR #253)

Installable Windows service: IRC nick **`console`** on **`#{machinename}`**.

## Behaviour

- Registers / identifies the `console` nick (password via file or `AIRC_CONSOLE_PASSWORD`)
- JOINs `#{COMPUTERNAME}` (creates channel when the network allows); **silent** in channel
- Direct PRIVMSG from authenticated operators opens a per-user shell session
- PRIVMSG text is piped to that console; stdout returns in Query (never on the shop channel)
- Empty operators/accounts refused

## Install (Windows + NSSM)

```powershell
# operators allowlist
Set-Content $env:USERPROFILE\.airc-console\operators.txt "Simon"

# optional NickServ / SASL password
# Set-Content $env:USERPROFILE\.airc-console\console.password "..."

powershell -NoProfile -ExecutionPolicy Bypass -File scripts\Install-AircConsole.ps1 `
  -PasswordFile $env:USERPROFILE\.airc-console\console.password

Start-Service AircConsole
```

Foreground smoke:

```powershell
powershell -File scripts\Start-AircConsole.ps1 -SelfTest
powershell -File scripts\Start-AircConsole.ps1 -Operators Simon
```

## Release

```powershell
powershell -File scripts\Pack-AircConsoleRelease.ps1
# -> dist/airc-console-<ver>.zip (+ .sha256)
```

GitHub Actions workflow `airc-console-release.yml` publishes tag `airc-console` (rolling) and immutable `airc-console-v*`.
