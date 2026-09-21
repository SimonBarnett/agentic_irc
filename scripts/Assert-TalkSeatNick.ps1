# Exit 0 when talk-seat nick suffix matches coordinator.pid seat= (PowerShell host PID).
param(
    [string]$IrcHome = $(Join-Path $env:USERPROFILE '.agentic-irc-cursor'),
    [string]$Scripts = 'C:\ai\agentic_irc\scripts'
)
$ErrorActionPreference = 'Stop'
$resolved = [Environment]::ExpandEnvironmentVariables($IrcHome)
$py = (Get-Command python -ErrorAction Stop).Source
$guard = Join-Path $Scripts 'talk_seat_pid.py'
& $py $guard --home $resolved
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$coordPath = Join-Path $resolved 'coordinator.pid'
if (-not (Test-Path -LiteralPath $coordPath)) { exit 0 }
$seatRaw = ''
foreach ($line in Get-Content -LiteralPath $coordPath) {
    if ($line -match '^seat=(\d+)$') { $seatRaw = $Matches[1] }
}
if (-not $seatRaw) { exit 0 }
$seatProc = Get-Process -Id ([int]$seatRaw) -ErrorAction SilentlyContinue
if (-not $seatProc) {
    Write-Output "INFO seat PowerShell PID $seatRaw is not running"
    exit 2
}
if ($seatProc.ProcessName -notmatch '^(powershell|pwsh)$') {
    Write-Output "INFO seat PID $seatRaw is $($seatProc.ProcessName), not PowerShell"
    exit 2
}
exit 0
