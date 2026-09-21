# Exit 0 when talk-seat nick suffix matches coordinator.pid agent= (authoritative).
param(
    [string]$IrcHome = $(Join-Path $env:USERPROFILE '.agentic-irc-cursor'),
    [string]$Scripts = 'C:\ai\agentic_irc\scripts'
)
$ErrorActionPreference = 'Stop'
$resolved = [Environment]::ExpandEnvironmentVariables($IrcHome)
$py = (Get-Command python -ErrorAction Stop).Source
$guard = Join-Path $Scripts 'talk_seat_pid.py'
& $py $guard --home $resolved
exit $LASTEXITCODE
