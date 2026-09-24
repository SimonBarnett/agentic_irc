# Exit 0 when talk-seat nick suffix matches coordinator.pid agent= (irc_agent PID).
param(
    [string]$IrcHome = $(Join-Path $env:USERPROFILE '.agentic-irc-cursor'),
    [string]$Scripts = $PSScriptRoot
)
$ErrorActionPreference = 'Stop'
$resolved = [Environment]::ExpandEnvironmentVariables($IrcHome)
$py = (Get-Command python -ErrorAction Stop).Source
$guard = Join-Path $Scripts 'talk_seat_pid.py'
& $py $guard --home $resolved
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$coordPath = Join-Path $resolved 'coordinator.pid'
if (-not (Test-Path -LiteralPath $coordPath)) { exit 0 }
$agentRaw = ''
foreach ($line in Get-Content -LiteralPath $coordPath) {
    if ($line -match '^agent=(\d+)$') { $agentRaw = $Matches[1] }
    elseif (-not $agentRaw -and $line -match '^seat=(\d+)$') { $agentRaw = $Matches[1] }
}
if (-not $agentRaw) { exit 0 }
$agentProc = Get-Process -Id ([int]$agentRaw) -ErrorAction SilentlyContinue
if (-not $agentProc) {
    Write-Output "INFO irc_agent PID $agentRaw is not running"
    exit 2
}
if ($agentProc.ProcessName -notmatch '^python') {
    Write-Output "INFO seat PID $agentRaw is $($agentProc.ProcessName), not python irc_agent"
    exit 2
}
exit 0
