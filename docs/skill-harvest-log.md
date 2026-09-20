# Skill harvest log

## 2026-09-21 — Ergo service BobIrcd

Ionos ircd is Windows service `BobIrcd` (`Start-Service BobIrcd`), not
task `BobIrcd-ionos`. NSSM + Automatic + LocalSystem. Recovery lives in
`.grok/skills/bob-irc`. `invite-airc` points at that service. Cert
recycle is `C:\ai\ergo\install-cert.ps1` (service, not the old task).

## 2026-09-20 — bob-irc lives here

Fleet Ergo playbook (`irc.ntsa.uk:6697`, connect.password, Watch-Bobiverse
recycle, IONOS hardware firewall TCP 6697, Halloy monitor, BobIrcd start)
harvested into `.grok/skills/bob-irc`. Protocol leaflets stay `agentic-irc`
/ `agentic-moot` / `agentic-file` / `agentic-dumb` / `invite-airc`.
`agentic_build` keeps a stub that points here. `install_skill.py` copies
`bob-irc` SKILL.md (no scripts dump).
