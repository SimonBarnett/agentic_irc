# Start or reuse irc_listen TSR for a talk-seat home. Writes coordinator.pid.
# Seat id: nick suffix and digest pid = seat= (coordinator PowerShell $PID), not listen=/agent=.
# Prefer scripts/Start-TalkSeat.ps1 to start agent + listener with correct nick.
# Do not use $Home (read-only). Does not start a second listener or irc_agent.
# Listen is one hidden python (CreateNoWindow). The child opens the log files
# itself so this launcher can exit. Not Start-Process -WindowStyle Hidden.
param(
    [string]$IrcHome = $(Join-Path $env:USERPROFILE '.agentic-irc-cursor'),
    [string]$Scripts = $PSScriptRoot,
    [string]$SeatPid = '',
    [string]$Nick = ''
)
$ErrorActionPreference = 'Stop'
. (Join-Path $Scripts 'IrcProcess.ps1')
$resolved = [Environment]::ExpandEnvironmentVariables($IrcHome)
if (-not (Test-Path -LiteralPath $resolved)) {
    New-Item -ItemType Directory -Force -Path $resolved | Out-Null
}
$coordPath = Join-Path $resolved 'coordinator.pid'
$existingSeat = ''
if (-not $SeatPid -and (Test-Path -LiteralPath $coordPath)) {
    foreach ($line in Get-Content -LiteralPath $coordPath) {
        if ($line -match '^seat=(.*)$') { $existingSeat = $Matches[1].Trim() }
    }
}
if (-not $SeatPid) { $SeatPid = $existingSeat }
$listen = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match 'irc_listen.py' -and $_.CommandLine -match [regex]::Escape($resolved) } |
    Select-Object -First 1
if (-not $listen) {
    $py = (Get-Command python -ErrorAction Stop).Source
    $listenPath = Join-Path $Scripts 'irc_listen.py'
    $stdoutLog = Join-Path $resolved 'listen.stdout.log'
    $stderrLog = Join-Path $resolved 'listen.stderr.log'
    $listenPid = Start-HiddenPython -Python $py -ArgumentList @(
        '-u', $listenPath, '--home', $resolved,
        '--stdout-log', $stdoutLog, '--stderr-log', $stderrLog
    ) -WorkingDirectory $Scripts
} else {
    $listenPid = $listen.ProcessId
}
$agent = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match 'irc_agent.py' -and $_.CommandLine -match [regex]::Escape($resolved) } |
    Select-Object -First 1
$agentPid = if ($agent) { $agent.ProcessId } else { '' }
if (-not $Nick -and $agent -and $agent.CommandLine -match '--nick\s+(\S+)') { $Nick = $Matches[1] }
$lines = @(
    "nick=$Nick"
    "listen=$listenPid"
    "agent=$agentPid"
    "home=$resolved"
)
if ($SeatPid) {
    $lines = @("nick=$Nick", "seat=$SeatPid", "listen=$listenPid", "agent=$agentPid", "home=$resolved")
}
$lines | Set-Content -LiteralPath $coordPath -Encoding utf8
Write-Output "INFO TSR listen=$listenPid agent=$agentPid seat=$SeatPid nick=$Nick log=$(Join-Path $resolved 'listen.stdout.log')"
