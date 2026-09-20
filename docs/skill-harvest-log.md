# Skill harvest log

## 2026-09-20 — Ionos Ergo start + firewall 6697

If `irc.ntsa.uk:6697` is down: `Start-ScheduledTask -TaskName 'BobIrcd-ionos'` (`C:\ai\ergo\ergo.exe`). Task Ready with no process means down. Windows Firewall inbound TCP 6697 (`Bobiverse IRC TLS 6697`). Do not open public `:6667`. Confirm dual-stack LISTEN and TLS `CN=irc.ntsa.uk`. IONOS panel firewall is a separate gate. Owner skill `agentic-irc`. Watch-Bobiverse stays `bob-irc` in `agentic_build`.
